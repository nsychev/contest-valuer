#!/usr/local/bin/python3.7
#
# Flexible postprocess script for scoring monitor in Yandex.Contest
#
# version: 5.1
# author:  Nikita Sychev (https://github.com/nsychev)
# release: November 27, 2023
# license: MIT
# url:     https://github.com/nsychev/contest-valuer

import itertools
import json
import os
import sys
import traceback

"""
Algorithm for getting test number. This should be either "sequential" or "smart".

"sequential" - Use sequence number of test in judging log. This doesn't work if
               you use “check until first fail in testset”, because some tests
               are skipped but sequence number are not.

"smart"      - Use test name to detect test number. This doesn't work if you
               have different folders for tests (e.g. tests/testset1/01,
               test/testset2/01, ...)
"""
TEST_EXTRACTION_MODE = "sequential"


class BadTestStringError(Exception):
    '''Exception of parsing string test specification'''
    
    def __init__(self, source, annotation = ''):
        self.msg = "Cannot parse string: `{0}`".format(source)
        if len(annotation) > 0:
            self.msg += "\n\n{0}".format(annotation)
    def __str__(self):
        return self.msg


def parseTests(tests):
    '''Parses test specification'''
    # <test_list> := <test_group>[,<test_list>]
    # <test_group> := <test> | <test>-<test>
    
    numbers = []
    
    intervals = [item.strip() for item in tests.split(",")]
    for interval in intervals:
        if len(interval) == 0:
            raise BadTestStringError(tests, "Empty interval")
        
        try:
            bounds = list(map(int, interval.split("-")))
        except Exception:
            raise BadTestStringError(tests, "Bad interval: `{}`".format(interval))
        
        if len(bounds) > 2:
            raise BadTestStringError(tests, "Interval `{}` contains more than two dash-separated integers".format(interval))
        
        left = bounds[0]
        right = bounds[-1]
        for test in range(left, right + 1):
            if test in numbers:
                raise BadTestStringError(tests, "Test `{}` is used more than once".format(test))
            numbers.append(test)
    
    return numbers


class Test:
    '''Object to store test info.'''
    
    def __init__(self, config):
        if TEST_EXTRACTION_MODE == "sequential":
            self.id = config.get("sequenceNumber", None)
        elif TEST_EXTRACTION_MODE == "smart":
            file_name = config.get("testName", "tests/0").split("/")[-1]
            self.id = int("".join(filter(str.isdigit, file_name)))
        else:
            raise ValueError(f"Unknown test extraction mode: {TEST_EXTRACTION_MODE}")
        self.verdict = config.get("verdict", "U").upper()
        self.full_verdict = config.get("verdict", "Unknown")
        if "-" in self.verdict:
            self.verdict = "".join(list(map(lambda word: word[0], self.verdict.split("-"))))
        self.time    = int(config.get("runningTime", 0))
        self.memory  = int(config.get("memoryUsed", 0))
        
        pointNode  = config.get("score", {})
        for key in pointNode:
            if key != "scoreType":
                self.points = pointNode[key]

    def passed(self):
        return self.verdict == "OK"
    
    def format_time(self):
        if self.time >= 1000:
            return "{0:>.2f} s".format(self.time / 1000.0)
        return "{0} ms".format(self.time)
  
    def format_memory(self):
        if self.memory > 2**23:
            return "{0} MB".format(self.memory // 2**20)
        if self.memory >= 2**20:
            return "{0:.1f} MB".format(self.memory / 2**20)
        if self.memory > 2**13:
            return "{0} KB".format(self.memory // 2**10)
        if self.memory >= 2**10:
            return "{0:.1f} KB".format(self.memory / 2**10)
        return "{0} bytes".format(self.memory)


def format_points(points, short=False):
    '''Formats points to human-readable format.'''
    if type(points) is float:
        spec = "{:.2f} {}"
    else:
        spec = "{} {}" + ("s" if points != 1 else "")
    return spec.format(
        points,
        "pt" if short else "point"
    )
    
    
class FeedbackMode:
    @staticmethod
    def state_only(name, passed, points, tests):
        return "{}: {}".format(name, "passed" if passed else "failed")
    
    @staticmethod
    def points(name, passed, points, tests):
        return "{}: {}, {}".format(
            name,
            "passed" if passed else "failed",
            format_points(points)
        )
        
    @staticmethod
    def verdicts(name, passed, points, tests):
        header = FeedbackMode.points(name, passed, points, tests)
        verdicts = " ".join(test.verdict for test in tests)
        return header + "\n" + verdicts

    @staticmethod
    def test_points(name, passed, points, tests):
        header = FeedbackMode.points(name, passed, points, tests)
        details = "\n".join(
            "{}: {} {}".format(test.id, test.verdict, format_points(test.points, short=True))
            for test in tests
        )
        return header + "\n" + details
    
    @staticmethod
    def first_failed(name, passed, points, tests):
        header = FeedbackMode.points(name, passed, points, tests)
        
        if passed:
            return header
        else:
            test = next(filter(lambda test: test.verdict != "OK", tests))
            
            details = "test {}: {}".format(test.id, test.full_verdict)
            
            return header + "\n" + details


def process_log(report):
    '''Processes Yandex.Contest run log.'''
    
    data = {}
    
    for test_object in report["tests"]:
        test = Test(test_object)
        data[test.id] = test

    return data


def process_config(tests):
    '''Processes JSON config'''
    
    final_score = 0
    passed_groups = []
    
    for item in os.listdir():
        if item.startswith("valuer") and item.endswith(".json") or item == "config.json":
            with open(item) as config_file:
                config = json.loads(config_file.read())
                break
    else:
        raise ValueError("Config file not found. Add config.json or valuer*.json file in postprocessor files.")

    for group_id, groupConfig in zip(itertools.count(), config):
        group = {
            "name": groupConfig.get("name", "group {}".format(group_id)),
            "tests": parseTests(groupConfig.get("tests", "")),
            "test_score": groupConfig.get("test_score", 0),
            "scoring_checker": groupConfig.get("scoring_checker", False),
            "full_score": groupConfig.get("full_score", 0),
            "required": groupConfig.get("required", False),
            "depends": groupConfig.get("depends", []),
            "feedback": groupConfig.get("feedback", "points")
        }
        
        skip = False
        for other_group in group["depends"]:
            if not(other_group in passed_groups):
                print("{}: skipped [required group {} failed]\n".format(group["name"], other_group), file=sys.stderr)
                skip = True
                break
        if skip:
            continue
        
        group_tests = []
        group_passed = True
        group_score = 0
        
        for test_id in group["tests"]:
            test = tests.get(test_id, Test({"testName": "tests/{}".format(test_id), "sequenceId": test_id}))
            group_tests.append(test)
            
            if test.verdict != "OK":
                group_passed = False
            elif group["scoring_checker"]:
                group_score += test.points
            else:
                group_score += group["test_score"]
            
        if group_passed:
            group_score += group["full_score"]
            passed_groups.append(group_id)
        
        final_score += group_score
        
        feedback_printer = getattr(FeedbackMode, group["feedback"])
        
        print(feedback_printer(group["name"], group_passed, group_score, group_tests), "\n", file=sys.stderr)
        
        if group["required"] and not group_passed:
            break
    
    return final_score


def main():
    try:
        report = json.loads(input())
        
        tests = process_log(report)
        score = process_config(tests)
        
        print(score)
        print("total:", format_points(score), file=sys.stderr)
    except Exception as e:
        print(-1)
        print("Postprocessor failed", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)

   
if __name__ == "__main__":
    main()

#!/usr/bin/python3.4
#
# Flexible postprocess script for scoring monitor in Yandex.Contest
#
# version: 4.1.1
# author:  Nikita Sychev (https://github.com/nsychev)
# release: January 25, 2019
# license: MIT
# url:     https://github.com/nsychev/contest-valuer

import itertools
import json
import sys
import traceback


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
        self.id      = config.get("sequenceNumber", None)
        self.verdict = config.get("verdict", "undefined").upper()
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
        if t >= 1000:
            return "{0:>.2f} s".format(t / 1000.0)
        return "{0} ms".format(t)
  
    def format_memory(self):
        if m > 2**23:
            return "{0} MB".format(m // 2**20)
        if m >= 2**20:
            return "{0:.1f} MB".format(m / 2**20)
        if m > 2**13:
            return "{0} KB".format(m // 2**10)
        if m >= 2**10:
            return "{0:.1f} KB".format(m / 2**10)
        return "{0} bytes".format(m)


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
    

FEEDBACK_MODES = {
    "state":    lambda name, passed, points, tests: "{}: {}".format(name, "passed" if passed else "failed"),
    "points":   lambda name, passed, points, tests: "{}: {}".format(name, format_points(points)),
    "verdicts": lambda name, passed, points, tests: "{}: {}\n".format(name, format_points(points)) + " ".join([
        test.verdict
        for test in tests
    ]),
    "test_points": lambda name, passed, points, tests: "{}: {}\n".format(name, format_points(points)) + "\n".join([
        "{}: {} {}".format(test.id, test.verdict, format_points(test.points, short=True))
        for test in tests
    ]),
    "full": lambda name, passed, points, tests: "{}: {}\n".format(name, format_points(points)) + "\n".join([
        "{}: {}, {}, {}".format(test.id, test.verdict, test.format_time(), test.format_memory())
        for test in tests
    ]),
    "full_points": lambda name, passed, points, tests: "{}: {}\n".format(name, format_points(points)) + "\n".join([
        "{}: {} {}, {}, {}".format(
            test.id, test.verdict, format_points(test.points, short=True), 
            test.format_time(), test.format_memory()
        )
        for test in tests
    ])
}


def process_log():
    '''Processes Yandex.Contest run log.'''
    
    data = {}
    report = json.loads(input())
    for test_object in report["tests"]:
        test = Test(test_object)
        data[test.id] = test
    return data


def process_config(tests):
    '''Processes JSON config'''
    
    final_score = 0
    passed_groups = []
    
    config = json.loads(open("config.json").read())

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
            test = tests.get(test_id, Test({"sequenceId": test_id}))
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
        print(FEEDBACK_MODES[group["feedback"]](group["name"], group_passed, group_score, group_tests), "\n", file=sys.stderr)
        
        if group["required"] and not group_passed:
            break
    
    return final_score


def main():
    try:
        tests = process_log()
        final_score = process_config(tests)
    except Exception as e:
        print(-239)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)

    print(final_score)
    print("total:", format_points(final_score), file=sys.stderr)

   
if __name__ == "__main__":
    main()

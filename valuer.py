#!/usr/bin/env python3.7
#
# Flexible postprocess script for scoring monitor in Yandex.Contest
#
# version: 5.2.0
# author:  Nikita Sychev (https://github.com/nsychev)
# release: July 14, 2025
# license: MIT
# url:     https://github.com/nsychev/contest-valuer

import itertools
import json
import os
import io
import sys
import traceback

TEST_EXTRACTION_MODE = "sequential"
"""
Algorithm for getting test number. This should be either "sequential" or "smart".

"sequential" - Use sequence number of test in judging log. This doesn't work if
               you use “check until first fail in testset”, because some tests
               are skipped but sequence number are not.

"smart"      - Use test name to detect test number. This doesn't work if you
               have different folders for tests (e.g. tests/testset1/01,
               tests/testset2/01, ...)
"""

FEEDBACK_MODE = "auto"
"""
Feedback verboity mode. This should be either "full", "compact" or "auto".

See `FEEDBACK_FULL` and `FEEDBACK_COMPACT` for details.

"auto" mode will use "full" mode if the output is less than 1024 characters,
and "compact" mode otherwise.
"""

FEEDBACK_FULL = {
    "GROUP": {
        "PREFIX": "- ",
        "POSTFIX": ": ",
    },
    "GROUP_POINTS": {
        "PREFIX": ", ",
        "POSTFIX": "",
    },
    "TEST_NUM": {
        "PREFIX": "test #",
        "POSTFIX": ": ",
    },
    "TEST_POINTS": {
        "PREFIX": ", ",
        "POSTFIX": "",
    },
    "TEST_VERDICT": {
        "PREFIX": "",
        "POSTFIX": "",
    },
    "VERDICTS": {
        "PREFIX": "verdicts: ",
        "POSTFIX": "",
        "JOINER": ", ",
    },
}
"""
Formatting for feedback messages with default values and full mode:

```
- sample: passed
- group1: passed, 30 points
- group2: passed, 60 points
          verdicts: OK, OK, OK
- group3: passed, 5 points
          test #10: OK, 10 points
          test #11: OK, 10 points
          test #12: OK, 10 points
- group4: failed, 0 points
          test #14: wrong-answer
total: 95 points
```

For config:
```json
[
    {
        "name": "sample",
        "testset": "samples",
        "required": true,
        "feedback": "state_only"
    },
    {
        "name": "group1",
        "testset": "1",
        "full_score": 30,
        "required": false,
        "feedback": "points"
    },
    {
        "name": "group2",
        "testset": "2",
        "full_score": 60,
        "required": false,
        "depends": [1],
        "feedback": "verdicts"
    },
    {
        "name": "group3",
        "testset": "3",
        "required": false,
        "depends": [1, 2],
        "full_score": 5,
        "feedback": "test_points"
    },
    {
        "name": "group4",
        "testset": "4",
        "required": false,
        "full_score": 5,
        "feedback": "first_failed"
    }
]
```
"""

FEEDBACK_COMPACT = {
    "GROUP": {
        "PREFIX": "",
        "POSTFIX": ": ",
    },
    "GROUP_POINTS": {
        "PREFIX": ", ",
        "POSTFIX": "",
    },
    "TEST_NUM": {
        "PREFIX": "test ",
        "POSTFIX": ": ",
    },
    "TEST_POINTS": {
        "PREFIX": ", ",
        "POSTFIX": "",
    },
    "TEST_VERDICT": {
        "PREFIX": "",
        "POSTFIX": "",
    },
    "VERDICTS": {
        "PREFIX": "",
        "POSTFIX": "",
        "JOINER": " ",
    },
}
"""
Formatting for compact feedback messages with default values and compact mode:

```
sample: passed
group1: passed, 30 pts
group2: passed, 60 pts
OK OK OK
group3: passed, 5 pts
test 10: OK, 10 pts
test 11: OK, 10 pts
test 12: OK, 10 pts
group4: failed, 0 pts
test 14: wrong-answer
total: 95 pts
```

For config:
```json
[
    {
        "name": "sample",
        "testset": "samples",
        "required": true,
        "feedback": "state_only"
    },
    {
        "name": "group1",
        "testset": "1",
        "full_score": 30,
        "required": false,
        "feedback": "points"
    },
    {
        "name": "group2",
        "testset": "2",
        "full_score": 60,
        "required": false,
        "depends": [1],
        "feedback": "verdicts"
    },
    {
        "name": "group3",
        "testset": "3",
        "required": false,
        "depends": [1, 2],
        "full_score": 5,
        "feedback": "test_points"
    },
    {
        "name": "group4",
        "testset": "4",
        "required": false,
        "full_score": 5,
        "feedback": "first_failed"
    }
]
```
"""

feedback_io_compact = io.StringIO()
feedback_io_full = io.StringIO()


class BadTestStringError(Exception):
    """Exception of parsing string test specification"""

    def __init__(self, source, annotation=""):
        self.msg = "Cannot parse string: `{0}`".format(source)
        if len(annotation) > 0:
            self.msg += "\n\n{0}".format(annotation)

    def __str__(self):
        return self.msg


def parseTests(tests):
    """Parses test specification"""
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
            raise BadTestStringError(
                tests,
                "Interval `{}` contains more than two dash-separated integers".format(interval),
            )

        left = bounds[0]
        right = bounds[-1]
        for test in range(left, right + 1):
            if test in numbers:
                raise BadTestStringError(tests, "Test `{}` is used more than once".format(test))
            numbers.append(test)

    return numbers


class Test:
    """Object to store test info."""

    def __init__(self, config):
        if TEST_EXTRACTION_MODE == "sequential":
            self.id = config.get("sequenceNumber", None)
        elif TEST_EXTRACTION_MODE == "smart":
            file_name = config.get("testName", "tests/0").split("/")[-1]
            self.id = int("".join(filter(str.isdigit, file_name)))
        else:
            raise ValueError(
                "Unknown test extraction mode: {}".format(TEST_EXTRACTION_MODE)
            )
        self.verdict = config.get("verdict", "U").upper()
        self.full_verdict = config.get("verdict", "Unknown")
        if "-" in self.verdict:
            self.verdict = "".join(
                list(map(lambda word: word[0], self.verdict.split("-")))
            )
        self.time = int(config.get("runningTime", 0))
        self.memory = int(config.get("memoryUsed", 0))
        self.testsetName = config.get("testsetName", "")

        pointNode = config.get("score", {})
        for key in pointNode:
            if key != "scoreType":
                self.points = pointNode[key]

    def passed(self):
        return self.verdict == "OK"


def format_points(points, short=False):
    """Formats points to human-readable format."""
    if type(points) is float:
        spec = "{:.2f} {}"
    else:
        spec = "{} {}" + ("s" if points != 1 else "")
    return spec.format(points, "pt" if short else "point")


class FeedbackMode:
    @staticmethod
    def state_only(name, passed, points, tests, feedback_mode):
        if feedback_mode == "full":
            return "{}{}{}{}".format(
                FEEDBACK_FULL["GROUP"]["PREFIX"],
                name,
                FEEDBACK_FULL["GROUP"]["POSTFIX"],
                "passed" if passed else "failed",
            )
        elif feedback_mode == "compact":
            return "{}{}{}{}".format(
                FEEDBACK_COMPACT["GROUP"]["PREFIX"],
                name,
                FEEDBACK_COMPACT["GROUP"]["POSTFIX"],
                "passed" if passed else "failed",
            )
        else:
            raise ValueError("Unknown feedback mode: {}".format(feedback_mode))

    @staticmethod
    def points(name, passed, points, tests, feedback_mode):
        if feedback_mode == "full":
            return "{}{}{}{}{}{}{}".format(
                FEEDBACK_FULL["GROUP"]["PREFIX"],
                name,
                FEEDBACK_FULL["GROUP"]["POSTFIX"],
                "passed" if passed else "failed",
                FEEDBACK_FULL["GROUP_POINTS"]["PREFIX"],
                format_points(points),
                FEEDBACK_FULL["GROUP_POINTS"]["POSTFIX"],
            )
        elif feedback_mode == "compact":
            return "{}{}{}{}{}{}{}".format(
                FEEDBACK_COMPACT["GROUP"]["PREFIX"],
                name,
                FEEDBACK_COMPACT["GROUP"]["POSTFIX"],
                "passed" if passed else "failed",
                FEEDBACK_COMPACT["GROUP_POINTS"]["PREFIX"],
                format_points(points, short=True),
                FEEDBACK_COMPACT["GROUP_POINTS"]["POSTFIX"],
            )
        else:
            raise ValueError("Unknown feedback mode: {}".format(feedback_mode))

    @staticmethod
    def verdicts(name, passed, points, tests, feedback_mode):
        if feedback_mode == "full":
            header = FeedbackMode.points(name, passed, points, tests, feedback_mode)
            verdicts = (
                len(
                    FEEDBACK_FULL["GROUP"]["PREFIX"]
                    + name
                    + FEEDBACK_FULL["GROUP"]["POSTFIX"]
                )
                * " "
                + FEEDBACK_FULL["VERDICTS"]["PREFIX"]
                + FEEDBACK_FULL["VERDICTS"]["JOINER"].join(
                    test.verdict for test in tests
                )
                + FEEDBACK_FULL["VERDICTS"]["POSTFIX"]
            )
            return header + "\n" + verdicts
        elif feedback_mode == "compact":
            header = FeedbackMode.points(name, passed, points, tests, feedback_mode)
            verdicts = (
                FEEDBACK_COMPACT["VERDICTS"]["PREFIX"]
                + FEEDBACK_COMPACT["VERDICTS"]["JOINER"].join(
                    test.verdict for test in tests
                )
                + FEEDBACK_COMPACT["VERDICTS"]["POSTFIX"]
            )
            return header + "\n" + verdicts
        else:
            raise ValueError("Unknown feedback mode: {}".format(feedback_mode))

    @staticmethod
    def test_points(name, passed, points, tests, feedback_mode):
        if feedback_mode == "full":
            header = FeedbackMode.points(name, passed, points, tests, feedback_mode)
            details = "\n".join(
                (
                    "{}{}{}{}{}{}{}".format(
                        len(
                            FEEDBACK_FULL["GROUP"]["PREFIX"]
                            + name
                            + FEEDBACK_FULL["GROUP"]["POSTFIX"]
                        )
                        * " ",
                        FEEDBACK_FULL["TEST_NUM"]["PREFIX"],
                        test.id,
                        FEEDBACK_FULL["TEST_NUM"]["POSTFIX"],
                        FEEDBACK_FULL["TEST_VERDICT"]["PREFIX"],
                        test.verdict,
                        FEEDBACK_FULL["TEST_VERDICT"]["POSTFIX"],
                    )
                    + (
                        (
                            FEEDBACK_FULL["TEST_POINTS"]["PREFIX"]
                            + format_points(test.points)
                        )
                        if hasattr(test, "points")
                        else ""
                    )
                )
                for test in tests
            )
            return header + "\n" + details
        elif feedback_mode == "compact":
            header = FeedbackMode.points(name, passed, points, tests, feedback_mode)
            details = "\n".join(
                (
                    "{}{}{}{}{}{}".format(
                        FEEDBACK_COMPACT["TEST_NUM"]["PREFIX"],
                        test.id,
                        FEEDBACK_COMPACT["TEST_NUM"]["POSTFIX"],
                        FEEDBACK_COMPACT["TEST_VERDICT"]["PREFIX"],
                        test.verdict,
                        FEEDBACK_COMPACT["TEST_VERDICT"]["POSTFIX"],
                    )
                    + (
                        (
                            FEEDBACK_COMPACT["TEST_POINTS"]["PREFIX"]
                            + format_points(test.points, short=True)
                        )
                        if hasattr(test, "points")
                        else ""
                    )
                )
                for test in tests
            )
            return header + "\n" + details
        else:
            raise ValueError("Unknown feedback mode: {}".format(feedback_mode))

    @staticmethod
    def first_failed(name, passed, points, tests, feedback_mode):
        if feedback_mode == "full":
            header = FeedbackMode.points(name, passed, points, tests, feedback_mode)
            if passed:
                return header
            else:
                test = next(filter(lambda test: test.verdict != "OK", tests))
                details = "{}{}{}{}{}{}{}".format(
                    len(
                        FEEDBACK_FULL["GROUP"]["PREFIX"]
                        + name
                        + FEEDBACK_FULL["GROUP"]["POSTFIX"]
                    )
                    * " ",
                    FEEDBACK_FULL["TEST_NUM"]["PREFIX"],
                    test.id,
                    FEEDBACK_FULL["TEST_NUM"]["POSTFIX"],
                    FEEDBACK_FULL["TEST_VERDICT"]["PREFIX"],
                    test.full_verdict,
                    FEEDBACK_FULL["TEST_VERDICT"]["POSTFIX"],
                )

                return header + "\n" + details
        elif feedback_mode == "compact":
            header = FeedbackMode.points(name, passed, points, tests, feedback_mode)
            if passed:
                return header
            else:
                test = next(filter(lambda test: test.verdict != "OK", tests))
                details = "{}{}{}{}{}{}".format(
                    FEEDBACK_COMPACT["TEST_NUM"]["PREFIX"],
                    test.id,
                    FEEDBACK_COMPACT["TEST_NUM"]["POSTFIX"],
                    FEEDBACK_COMPACT["TEST_VERDICT"]["PREFIX"],
                    test.full_verdict,
                    FEEDBACK_COMPACT["TEST_VERDICT"]["POSTFIX"],
                )

                return header + "\n" + details
        else:
            raise ValueError("Unknown feedback mode: {}".format(feedback_mode))


def process_log(report):
    """Processes Yandex.Contest run log."""

    data = {}

    for test_object in report["tests"]:
        test = Test(test_object)
        data[test.id] = test

    return data


def process_config(tests):
    """Processes JSON config"""

    final_score = 0
    passed_groups = []

    for item in os.listdir():
        if (
            item.startswith("valuer")
            and item.endswith(".json")
            or item == "config.json"
        ):
            with open(item) as config_file:
                config = json.loads(config_file.read())
                break
    else:
        raise ValueError(
            "Config file not found. Add config.json or valuer*.json file in postprocessor files."
        )

    for group_id, groupConfig in zip(itertools.count(), config):
        group = {
            "name": groupConfig.get("name", "group {}".format(group_id)),
            "tests": groupConfig.get("tests"),
            "testset": groupConfig.get("testset"),
            "test_score": groupConfig.get("test_score", 0),
            "scoring_checker": groupConfig.get("scoring_checker", False),
            "full_score": groupConfig.get("full_score", 0),
            "required": groupConfig.get("required", False),
            "depends": groupConfig.get("depends", []),
            "feedback": groupConfig.get("feedback", "points"),
        }

        skip = False
        for other_group in group["depends"]:
            if other_group not in passed_groups:
                if FEEDBACK_MODE == "compact":
                    print(
                        "{}{}{}skipped [required group {} failed]".format(
                            FEEDBACK_COMPACT["GROUP"]["PREFIX"],
                            group["name"],
                            FEEDBACK_COMPACT["GROUP"]["POSTFIX"],
                            other_group,
                        ),
                        file=feedback_io_compact,
                    )
                elif FEEDBACK_MODE == "full":
                    print(
                        "{}{}{}skipped [required group {} failed]".format(
                            FEEDBACK_FULL["GROUP"]["PREFIX"],
                            group["name"],
                            FEEDBACK_FULL["GROUP"]["POSTFIX"],
                            other_group,
                        ),
                        file=feedback_io_full,
                    )
                else:
                    print(
                        "{}{}{}skipped [required group {} failed]".format(
                            FEEDBACK_COMPACT["GROUP"]["PREFIX"],
                            group["name"],
                            FEEDBACK_COMPACT["GROUP"]["POSTFIX"],
                            other_group,
                        ),
                        file=feedback_io_compact,
                    )
                    print(
                        "{}{}{}skipped [required group {} failed]".format(
                            FEEDBACK_FULL["GROUP"]["PREFIX"],
                            group["name"],
                            FEEDBACK_FULL["GROUP"]["POSTFIX"],
                            other_group,
                        ),
                        file=feedback_io_full,
                    )

                skip = True
                break
        if skip:
            continue

        group_tests = []
        group_passed = True
        group_score = 0

        if group["tests"] is None and group["testset"] is None:
            raise ValueError(
                "You should define either 'tests' or 'testset' key in each group, none found in {}".format(
                    group["name"]
                )
            )
        if group["tests"] is not None and group["testset"] is not None:
            raise ValueError(
                "You should define either 'tests' or 'testset' key in each group, both found in {}".format(
                    group["name"]
                )
            )

        if group["tests"] is not None:
            for test_id in parseTests(group["tests"]):
                test = tests.get(
                    test_id,
                    Test(
                        {"testName": "tests/{}".format(test_id), "sequenceId": test_id}
                    ),
                )
                group_tests.append(test)

        if group["testset"] is not None:
            for test in tests.values():
                if test.testsetName == group["testset"]:
                    group_tests.append(test)

        for test in group_tests:
            if test.verdict != "OK":
                group_passed = False
            elif group["scoring_checker"]:
                group_score += test.points
            else:
                group_score += group["test_score"]

        if len(group_tests) == 0:
            group_passed = False

        if group_passed:
            group_score += group["full_score"]
            passed_groups.append(group_id)

        final_score += group_score

        feedback_printer = getattr(FeedbackMode, group["feedback"])

        if FEEDBACK_MODE == "compact":
            feedback_compact = feedback_printer(
                group["name"], group_passed, group_score, group_tests, "compact"
            )
            print(feedback_compact, file=feedback_io_compact)
        elif FEEDBACK_MODE == "full":
            feedback_full = feedback_printer(
                group["name"], group_passed, group_score, group_tests, "full"
            )
            print(feedback_full, file=feedback_io_full)
        else:
            feedback_compact = feedback_printer(
                group["name"], group_passed, group_score, group_tests, "compact"
            )
            feedback_full = feedback_printer(
                group["name"], group_passed, group_score, group_tests, "full"
            )
            print(feedback_compact, file=feedback_io_compact)
            print(feedback_full, file=feedback_io_full)

        if group["required"] and not group_passed:
            break

    return final_score


def main():
    try:
        report = json.loads(input())

        tests = process_log(report)
        score = process_config(tests)

        print(score)

        print("total:", format_points(score, short=True), file=feedback_io_compact)
        print("total:", format_points(score), file=feedback_io_full)
        if FEEDBACK_MODE == "compact":
            print(feedback_io_compact.getvalue(), file=sys.stderr, end="")
        elif FEEDBACK_MODE == "full":
            print(feedback_io_full.getvalue(), file=sys.stderr, end="")
        else:
            if len(feedback_io_full.getvalue()) < 1024:
                print(feedback_io_full.getvalue(), file=sys.stderr, end="")
            else:
                print(feedback_io_compact.getvalue(), file=sys.stderr, end="")

    except Exception as _:
        print(-1)
        print("Postprocessor failed", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

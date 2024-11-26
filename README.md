# Contest Valuer

This is the postprocess script I use in my contests in [Yandex Contest](https://contest.yandex.com/) system.

## Features

- can be adjusted for various scoring systems
- scoring per test
- group scoring
- checker scoring
- group dependencies
- different styles of feedback for participant
- custom reports

## Usage

1. Create JSON config with postprocessor configuration. It should be named either `config.json` or `valuer*.json` (`*` means any characters).
2. Upload [valuer.py](valuer.py) and config file to your problem
3. Add these files to section “Postprocessing files”

## Configuration Examples

[Russian Olympiad in Informatics, 2024, Regional Stage, Day 1, Problem 1](https://nerc.itmo.ru/school/archive/2023-2024/ru-olymp-regional-2024-day1.pdf): five testsets, only complete testsets are scored, the last group is scored only if first four passed.

```json
[
  {"name": "samples", "feedback": "state_only", "tests": "1-5"},
  {"feedback": "first_failed", "full_score": 15, "tests": "6-20", "depends": []},
  {"feedback": "first_failed", "full_score": 16, "tests": "21-36", "depends": []},
  {"feedback": "first_failed", "full_score": 17, "tests": "37-52", "depends": []},
  {"feedback": "first_failed", "full_score": 18, "tests": "53-68", "depends": []},
  {"feedback": "first_failed", "full_score": 34, "tests": "69-98", "depends": [1, 2, 3, 4]}
]
```

[Russiaon Olympiad in Informatics, 2022, Regional Stage, Day 1, Problem 3](https://nerc.itmo.ru/school/archive/2021-2022/ru-olymp-regional-2022-day1.pdf): 22 tests, each test except for samples worth 5 points.

```
[
  {"tests": "1-2", "name": "samples", "feedback": "state_only"},
  {"tests": "3-22", "feedback": "verdicts", "test_score": 5}
]
```

## Configuration

All configuration is inside one JSON file — `config.json`. It consists of array of `Group` objects.

### Group

Object which may contain these fields:

Field | Type | Description | Default value
--- | --- | --- | ---
name | string | Name of this group | `"group {#id}"`
tests | TestList | Group tests | —
testset | string | Name of testset in Yandex Contest | —
test_score | int | Points for each OK test | `0`
scoring_checker | bool | If `True`, checker points are used for scoring | `False`
full_score | int | Points if group is passed | `0`
required | bool | If `True` and group is not passed, valuer won’t score next groups | `False`
depends | int[] | If any group from list is not passed, valuer won’t score this group | `[]`
feedback | FeedbackType | Style of information in report | `"points"`

Either `tests` or `testset` is required.

> **Note**: Groups are indexed from zero.

> **Note**: `test_score` is ignored when using `check_partial`

### TestList

String which satisfies grammar and describes set of tests:

```
<test_list> := <test_group>[,<test_list>]
<test_group> := <test> | <test>-<test>
```

### Feedback

One of strings from list:

Name | Meaning
--- | ---
state_only | Passed or failed for whole group
points | Points for whole group
verdicts | `points` + verdict for each test
test_points | `verdicts` + points for each test
first_failed | `points` + verdict for first failed test

> **Note**: Even if you use `state` report for some groups, participant will see his final score.

### License

[MIT License](LICENSE) is applied to this repository.

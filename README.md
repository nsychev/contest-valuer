# Contest Valuer

This is the postprocess script I use in my contests in [Yandex.Contest](https://contest.yandex.ru/) system.

## Features

- can be adjusted for various scoring systems
- scoring per test
- group scoring
- supported checker scoring
- “required” groups
- different styles of feedback for participant
- custom reports

## Usage

1. Create JSON config and rename it to `config.json`
2. Upload [valuer.py](valuer.py) and `config.json` to the root of your problem
3. Add these files to section “Postprocessing files”

## Configuration

All configuration is inside one JSON file — `config.json`. It consists of array of `Group` objects.

### Group

Object which may contain these fields:

Field | Type | Description | Default value
--- | --- | --- | ---
name | string | Custom name of this group | `group {#id}`
tests | TestList | Group tests | **required**
test_score | int | Points for each OK test | `0`
check_partial | bool | If `True`, checker points are used for scoring.  `test_score` is ignored therefore | `False`
full_score | int | Points if group is passed | `0`
required | bool | If `True` and group is not passed, valuer won’t score next groups | `False`
depends | int[] | If any group from list is not passed, valuer won’t score this group | `[]`
feedback | FeedbackType | Style of information in report | `"points"`

> **Note**: Groups are indexed from zero.

## TestList

String which satisfies grammar and describes group tests:

```
<test_list> := <test_group>[,<test_list>]
<test_group> := <test> | <test>-<test>
```

## Feedback

One of strings from list:

Name | Meaning
--- | ---
state | Passed or failed
points | Points for whole subgroup
verdicts | `points` + verdict for each test
test_points | `verdicts` + points for each test
full | `verdicts` + time and memory for each test
full_points | `full` + points for each test

> **Note**: Even if you use `state` report for some groups, participant will see his final score.

## License

[MIT License](LICENSE) is applied to this repository.

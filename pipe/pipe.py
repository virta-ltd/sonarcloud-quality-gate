#!/usr/bin/env python

import json
import os
import re
import requests
from requests.auth import HTTPBasicAuth
import sys
import time

from bitbucket_pipes_toolkit import Pipe, get_variable

DEFAULT_TIMEOUT_SECONDS = 300
POLL_INTERVAL_SECONDS = 5


class QualityCheckError(BaseException):
    def __init__(self, message):
        self.message = message


def get_scanner_report_path():
    return "{}/sonarsource/sonarcloud-scan/sonarcloud-scan.log".format(os.environ['BITBUCKET_PIPE_SHARED_STORAGE_DIR'])


def get_scanner_report_text(scanner_report_path):
    """
    >>> get_scanner_report_text("/nonexistent")
    Traceback (most recent call last):
      ...
    pipe.QualityCheckError: Could not get scanner report: [Errno 2] No such file or directory: '/nonexistent'

    """
    try:
        with open(scanner_report_path) as fh:
            return fh.read()
    except Exception as e:
        raise QualityCheckError('Could not get scanner report: {}'.format(e))


def extract_ce_task_url(scanner_report_text):
    """
    >>> extract_ce_task_url("foo\\nINFO: More about the report processing at https://sonarcloud.io/api/ce/task?id=AWsm6vSHvzfVeZRohhkI\\nbar")
    'https://sonarcloud.io/api/ce/task?id=AWsm6vSHvzfVeZRohhkI'

    >>> extract_ce_task_url("foo")
    Traceback (most recent call last):
      ...
    pipe.QualityCheckError: Could not find compute engine task URL in scanner report

    >>> s = 'INFO: More about the report processing at https://sonarcloud.io/api/ce/task?id=AWsm6vSHvzfVeZRohhkI'
    >>> extract_ce_task_url("foo\\n{}\\n{}\\nbar".format(s, s))
    'https://sonarcloud.io/api/ce/task?id=AWsm6vSHvzfVeZRohhkI'

    """
    match = re.search(r'More about the report processing at (.*)', scanner_report_text)
    if match:
        return match.group(1)

    raise QualityCheckError("Could not find compute engine task URL in scanner report")


def extract_project_url(scanner_report_text):
    """
    >>> line_with_project_url = 'INFO: ANALYSIS SUCCESSFUL, you can browse https://sonarcloud.io/dashboard?id=janos-ss-team_upvotejs&branch=feature%2Ffailing-qg&resolved=false'
    >>> extract_project_url("foo\\n{}\\nbar".format(line_with_project_url))
    'https://sonarcloud.io/dashboard?id=janos-ss-team_upvotejs&branch=feature%2Ffailing-qg&resolved=false'

    >>> extract_project_url("foo")

    >>> extract_project_url("foo\\n{}\\n{}\\nbar".format(line_with_project_url, line_with_project_url))
    'https://sonarcloud.io/dashboard?id=janos-ss-team_upvotejs&branch=feature%2Ffailing-qg&resolved=false'

    """
    match = re.search(r'ANALYSIS SUCCESSFUL, you can browse (.*)', scanner_report_text)
    if match:
        return match.group(1)

    return None


def compute_max_retry_count(poll_interval_seconds, timeout_seconds):
    """
    >>> compute_max_retry_count(5, 300)
    60

    >>> compute_max_retry_count(5, 301)
    60

    >>> compute_max_retry_count(5, 2)
    0

    """
    return timeout_seconds // poll_interval_seconds


class FailedCondition:
    rating_labels = {
        1: 'A',
        2: 'B',
        3: 'C',
        4: 'D',
        5: 'E'
    }

    def __init__(self, obj):
        try:
            self.metric_key = obj['metricKey']
            self.comparator = obj['comparator']
            self.error_threshold = obj['errorThreshold']
            self.value = obj['actualValue']
        except:
            raise QualityCheckError("Could not parse failed condition from json: {}".format(json.dumps(obj)))

    def _simple_format(self):
        operator = 'less' if self.comparator == 'LT' else 'greater'
        return '{}: {} (is {} than {})'.format(self.metric_key, self.value, operator, self.error_threshold)

    def format(self, metric):
        """
        >>> c_rating = FailedCondition({'metricKey': 'rating', 'comparator': 'LT', 'errorThreshold': '1', 'actualValue': '3'})
        >>> c_rating.format(None)
        'rating: 3 (is less than 1)'

        >>> c_rating.format(Metric({'name': 'Foo', 'type': 'RATING'}))
        'Foo: C (is worse than A)'

        >>> c_rating.format(Metric({'name': 'Foo', 'type': 'foo'}))
        'Foo: 3 (is less than 1)'

        """
        if metric is None:
            return self._simple_format()

        if metric.metric_type == 'RATING':
            return '{}: {} (is worse than {})'.format(metric.name, self._rating_label(self.value), self._rating_label(self.error_threshold))

        operator = 'less' if self.comparator == 'LT' else 'greater'
        return '{}: {} (is {} than {})'.format(metric.name, self.value, operator, self.error_threshold)

    def _rating_label(self, value):
        int_value = int(float(str(value)))
        return self.rating_labels.get(int_value, value)


class QualityGateStatus:
    def __init__(self, obj):
        """
        >>> obj = {'projectStatus': {'status': 'ERROR', 'conditions': [{'status': 'ERROR', 'metricKey': 'new_reliability_rating', 'comparator': 'GT', 'periodIndex': 1, 'errorThreshold': '1', 'actualValue': '3'}, {'status': 'ERROR', 'metricKey': 'new_security_rating', 'comparator': 'GT', 'periodIndex': 1, 'errorThreshold': '1', 'actualValue': '2'}, {'status': 'OK', 'metricKey': 'new_maintainability_rating', 'comparator': 'GT', 'periodIndex': 1, 'errorThreshold': '1', 'actualValue': '1'}, {'status': 'OK', 'metricKey': 'new_coverage', 'comparator': 'LT', 'periodIndex': 1, 'errorThreshold': '80', 'actualValue': '0.0'}, {'status': 'OK', 'metricKey': 'new_duplicated_lines_density', 'comparator': 'GT', 'periodIndex': 1, 'errorThreshold': '3', 'actualValue': '0.0'}], 'periods': [{'index': 1, 'mode': 'days', 'date': '2019-06-03T17:47:41+0200', 'parameter': '30'}], 'ignoredConditions': True}}
        >>> s = QualityGateStatus(obj)
        >>> s.status, [c.metric_key for c in s.failed_conditions]
        ('ERROR', ['new_reliability_rating', 'new_security_rating'])

        """
        try:
            self.status = obj['projectStatus']['status']

            conditions = obj['projectStatus']['conditions']
            self.failed_conditions = [FailedCondition(c) for c in conditions if c['status'] == 'ERROR']
        except:
            raise QualityCheckError("Could not parse quality gate status from json: {}".format(json.dumps(obj)))


class CeTask:
    def __init__(self, obj):
        """
        >>> CeTask({"task": {"status": "IN_PROGRESS"}}).is_completed()
        False
        """
        try:
            self.status = obj['task']['status']
            self.completed = self.status not in ('IN_PROGRESS', 'PENDING')
            self.analysis_id = obj['task'].get('analysisId')
        except:
            raise QualityCheckError("Could not parse compute engine task from json: {}".format(json.dumps(obj)))

    def is_completed(self):
        return self.completed


class Metric:
    def __init__(self, obj):
        try:
            self.name = obj['name']
            self.metric_type = obj['type']
        except:
            raise QualityCheckError("Could not parse metric from json: {}".format(json.dumps(obj)))


class MetricsRepository:
    def __init__(self, obj=None, metric_keys=None):
        if obj is None:
            return

        try:
            self.metrics = {o['key']: Metric(o) for o in obj['metrics'] if o['key'] in metric_keys}
        except:
            raise QualityCheckError("Could not parse metrics from json: {}".format(json.dumps(obj)))

    def get(self, metric_key):
        return self.metrics[metric_key]


class SonarCloudClient:
    def __init__(self, sonar_token):
        self.sonar_token = sonar_token

    def _get_response_as_dict(self, url, error_message_prefix):
        req = requests.get(url, auth=HTTPBasicAuth(self.sonar_token, ''))
        if req.status_code != 200:
            try:
                errors_as_dict = req.json()
                errors_summary = '; '.join([e['msg'] for e in errors_as_dict['errors']])
                raise QualityCheckError("{}: {}".format(error_message_prefix, errors_summary))
            except:
                content = req.content
                raise QualityCheckError("{}: {}".format(error_message_prefix, content))

        return req.json()

    def get_ce_task(self, url):
        return CeTask(self._get_response_as_dict(url, "Could not fetch compute engine task"))

    def get_quality_gate_status(self, url):
        return QualityGateStatus(self._get_response_as_dict(url, "Could not fetch quality gate status"))

    def get_metrics(self, metric_keys):
        url = 'https://sonarcloud.io/api/metrics/search?ps=500'
        try:
            return MetricsRepository(self._get_response_as_dict(url, "ignored"), metric_keys)
        except QualityGateStatus:
            return MetricsRepository()


def create_ce_task_getter(client, ce_task_url):
    return lambda: client.get_ce_task(ce_task_url)


def wait_for_completed_ce_task(ce_task_getter, max_retry_count, poll_interval_seconds=POLL_INTERVAL_SECONDS):
    """
    >>> ce_task_getter = lambda obj: lambda: CeTask(obj)
    >>> wait_for_completed_ce_task(ce_task_getter({'task': {'status': 'PENDING', 'analysisId': 'foo'}}), 3, 0)
    Traceback (most recent call last):
      ...
    pipe.QualityCheckError: Compute engine task did not complete within time

    >>> wait_for_completed_ce_task(ce_task_getter({'task': {'status': 'IN_PROGRESS', 'analysisId': 'foo'}}), 3, 0)
    Traceback (most recent call last):
      ...
    pipe.QualityCheckError: Compute engine task did not complete within time

    >>> wait_for_completed_ce_task(ce_task_getter({'task': {'status': 'SUCCESS', 'analysisId': 'foo'}}), 3, 0).status
    'SUCCESS'

    >>> wait_for_completed_ce_task(ce_task_getter({'task': {'status': 'bar', 'analysisId': 'foo'}}), 3, 0).status
    'bar'

    """
    for _ in range(1 + max_retry_count):
        ce_task = ce_task_getter()
        if ce_task.is_completed():
            return ce_task

        print('.', end='')

        time.sleep(poll_interval_seconds)

    raise QualityCheckError("Compute engine task did not complete within time")


def get_quality_gate_status_url(ce_task):
    return "https://sonarcloud.io/api/qualitygates/project_status?analysisId={}".format(ce_task.analysis_id)


def main(pipe):
    sonar_token = get_variable('SONAR_TOKEN', required=True)
    timeout_seconds = get_variable('SONAR_QUALITY_GATE_TIMEOUT', required=False, default=DEFAULT_TIMEOUT_SECONDS)

    client = SonarCloudClient(sonar_token)

    scanner_report_path = get_scanner_report_path()
    scanner_report_text = get_scanner_report_text(scanner_report_path)
    ce_task_url = extract_ce_task_url(scanner_report_text)

    max_retry_count = compute_max_retry_count(POLL_INTERVAL_SECONDS, timeout_seconds)
    ce_task = wait_for_completed_ce_task(create_ce_task_getter(client, ce_task_url), max_retry_count)

    quality_gate_status_url = get_quality_gate_status_url(ce_task)
    quality_gate_status = client.get_quality_gate_status(quality_gate_status_url)

    project_url = extract_project_url(scanner_report_text)
    if project_url:
        project_url_suffix = "\nSee more details on SonarCloud: {}".format(project_url)
    else:
        project_url_suffix = ''

    if quality_gate_status.status == 'OK':
        pipe.success("Quality Gate passed" + project_url_suffix, do_exit=True)

    elif quality_gate_status.status == 'ERROR':
        metric_keys = set(c.metric_key for c in quality_gate_status.failed_conditions)
        metrics = client.get_metrics(metric_keys)

        message = "Quality Gate failed\n"

        for failed_condition in quality_gate_status.failed_conditions:
            metric = metrics.get(failed_condition.metric_key)
            message += "- {}\n".format(failed_condition.format(metric))

        pipe.fail(message + project_url_suffix)

    else:
        pipe.fail("Could not check Quality Gate status" + project_url_suffix)


if __name__ == '__main__':
    pipe = Pipe(pipe_metadata='/usr/bin/pipe.yml')

    try:
        main(pipe)
    except QualityCheckError as e:
        pipe.fail("Quality Gate failed: {}".format(e))
    except Exception as e:
        pipe.fail("Unknown error: {}".format(e))

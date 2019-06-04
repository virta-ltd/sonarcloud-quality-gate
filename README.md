# Bitbucket Pipelines Pipe: SonarCloud quality gate

TODO

## YAML Definition

Add the following snippet to the script section of your `bitbucket-pipelines.yml` file:

```yaml
- pipe: sonarsource/sonarcloud-quality-gate:0.0.1
  variables:
    TIMEOUT: 300  # 5 minutes
```

## Variables

| Variable           | Usage                                                       |
| --------------------- | ----------------------------------------------------------- |
| SONAR_TOKEN (*) | SonarCloud token. It is recommended to use a secure repository or account variable.  |
| TIMEOUT | Maximum seconds to wait to get quality gate status |

_(*) = required variable._

## Details

TODO

## Prerequisites

To use this pipe you must have the SonarCloud Scan pipe earlier in the pipeline.

## Examples

Basic example:

```yaml
- pipe: sonarsource/sonarcloud-quality-gate:0.1.0
  variables:
    TIMEOUT: 300
```

## Support

If you would like help with this pipe, or you have an issue or feature request, [let us know on our community forum](https://community.sonarsource.com/tags/c/help/sc/bitbucket).

If you are reporting an issue, please include:

* the version of the pipe
* relevant logs and error messages
* steps to reproduce

Releasing a new version
=======================

This pipe uses an automated release process to bump versions using semantic versioning and generate the CHANGELOG.md file automatically. 

In order to automate this process it uses a tool called [`semversioner`](https://pypi.org/project/semversioner/). 

Steps to release
----------------

Follow the steps in [develop.md](develop.md) regarding bumping the version and validating a pull request.

After a pull request has been validated:

1) Merge the pull request to `master`

2) Run the `release` pipe manually

The pipeline will:

- Generate new version number based on the changeset types `major`, `minor`, `patch`.
- Generate a new file in `.changes` directory with all the changes for this specific version.
- (Re)generate the CHANGELOG.md file.
- Bump the version number in `README.md` example and `pipe.yml` metadata.
- Commit and push back to the repository.
- Tag your commit with the new version number.

3) Create a pull request on the [official pipes][official-pipes] repo to get the updated version featured in the sidebar.

[official-pipes]: https://bitbucket.org/bitbucketpipelines/official-pipes
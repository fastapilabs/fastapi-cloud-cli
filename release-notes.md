# Release Notes

## Latest Changes

### Fixes

* 🐛 Fix CI ran all tests on oldest supported Python. PR [#136](https://github.com/fastapilabs/fastapi-cloud-cli/pull/136) by [@DoctorJohn](https://github.com/DoctorJohn).

### Refactors

* ♻️ Reorder log messages for deployment readiness. PR [#137](https://github.com/fastapilabs/fastapi-cloud-cli/pull/137) by [@alejsdev](https://github.com/alejsdev).

### Upgrades

* ➖ Drop support for Pydantic v1. PR [#139](https://github.com/fastapilabs/fastapi-cloud-cli/pull/139) by [@patrick91](https://github.com/patrick91).
* 🔧 Drop support for Python 3.8. PR [#138](https://github.com/fastapilabs/fastapi-cloud-cli/pull/138) by [@patrick91](https://github.com/patrick91).

### Internal

* 👷 Configure coverage, error on main tests, don't wait for Smokeshow. PR [#134](https://github.com/fastapilabs/fastapi-cloud-cli/pull/134) by [@YuriiMotov](https://github.com/YuriiMotov).
* 👷 Run Smokeshow always, even on test failures. PR [#133](https://github.com/fastapilabs/fastapi-cloud-cli/pull/133) by [@YuriiMotov](https://github.com/YuriiMotov).

## 0.7.0

### Features

* ✨ Add upload cancellation notification on keyboard interrupt. PR [#129](https://github.com/fastapilabs/fastapi-cloud-cli/pull/129) by [@patrick91](https://github.com/patrick91).

### Fixes

* 🐛 Handle TimeoutError when waiting for deployment. PR [#131](https://github.com/fastapilabs/fastapi-cloud-cli/pull/131) by [@buurro](https://github.com/buurro).

### Internal

* ✅ Fix test coverage. PR [#130](https://github.com/fastapilabs/fastapi-cloud-cli/pull/130) by [@patrick91](https://github.com/patrick91).

## 0.6.0

### Features

* ⚡️ Compress code archives to speed up uploads. PR [#125](https://github.com/fastapilabs/fastapi-cloud-cli/pull/125) by [@DoctorJohn](https://github.com/DoctorJohn).

### Refactors

* ⬆️ Migrate to uv. PR [#127](https://github.com/fastapilabs/fastapi-cloud-cli/pull/127) by [@DoctorJohn](https://github.com/DoctorJohn).
* 🔥 Remove path confirmation on first deployment. PR [#123](https://github.com/fastapilabs/fastapi-cloud-cli/pull/123) by [@buurro](https://github.com/buurro).

## 0.5.2

### Fixes

* 🐛 Fix archive file was not closed after upload. PR [#122](https://github.com/fastapilabs/fastapi-cloud-cli/pull/122) by [@DoctorJohn](https://github.com/DoctorJohn).

## 0.5.1

### Fixes

* ✏️ Fix logout suggestion message. PR [#118](https://github.com/fastapilabs/fastapi-cloud-cli/pull/118) by [@buurro](https://github.com/buurro).

### Refactors

* ♻️ Improve waitlist success command. PR [#117](https://github.com/fastapilabs/fastapi-cloud-cli/pull/117) by [@patrick91](https://github.com/patrick91).

## 0.5.0

### Features

* ✨ Resume build log stream if interrupted. PR [#109](https://github.com/fastapilabs/fastapi-cloud-cli/pull/109) by [@buurro](https://github.com/buurro).

### Internal

* 👷 Add support for Pydantic v1. PR [#116](https://github.com/fastapilabs/fastapi-cloud-cli/pull/116) by [@patrick91](https://github.com/patrick91).
* 🔧 Add labels to Dependabot updates. PR [#113](https://github.com/fastapilabs/fastapi-cloud-cli/pull/113) by [@alejsdev](https://github.com/alejsdev).

## 0.4.0

### Features

* ✨ Add fastapi cloud sub-command. PR [#104](https://github.com/fastapilabs/fastapi-cloud-cli/pull/104) by [@buurro](https://github.com/buurro).
* ✨ Check if token is expired when checking if user is logged in. PR [#105](https://github.com/fastapilabs/fastapi-cloud-cli/pull/105) by [@patrick91](https://github.com/patrick91).
* ✨ Support the verification skipped status. PR [#99](https://github.com/fastapilabs/fastapi-cloud-cli/pull/99) by [@DoctorJohn](https://github.com/DoctorJohn).

### Fixes

* 🐛 Include hidden files in app archive. PR [#115](https://github.com/fastapilabs/fastapi-cloud-cli/pull/115) by [@buurro](https://github.com/buurro).
* ♻️  Clean up code archives after uploading. PR [#106](https://github.com/fastapilabs/fastapi-cloud-cli/pull/106) by [@DoctorJohn](https://github.com/DoctorJohn).

### Refactors

* 🧑‍💻 Handle already logged in state. PR [#103](https://github.com/fastapilabs/fastapi-cloud-cli/pull/103) by [@alejsdev](https://github.com/alejsdev).
* ⚡️ Speed up archive creation. PR [#111](https://github.com/fastapilabs/fastapi-cloud-cli/pull/111) by [@DoctorJohn](https://github.com/DoctorJohn).

## 0.3.1

### Fixes

* 🐛 Fix login url not linked correctly. PR [#89](https://github.com/fastapilabs/fastapi-cloud-cli/pull/89) by [@patrick91](https://github.com/patrick91).

### Refactors

* ♻️ Refactor env vars creation . PR [#92](https://github.com/fastapilabs/fastapi-cloud-cli/pull/92) by [@alejsdev](https://github.com/alejsdev).
* 🔥 Remove env vars from deploy workflow. PR [#93](https://github.com/fastapilabs/fastapi-cloud-cli/pull/93) by [@alejsdev](https://github.com/alejsdev).

### Internal

* ♻️ Log files added to archive in debug mode (#91). PR [#96](https://github.com/fastapilabs/fastapi-cloud-cli/pull/96) by [@patrick91](https://github.com/patrick91).
* ✅ Add test to make sure .fastapicloudignore can override .gitignore (#90). PR [#95](https://github.com/fastapilabs/fastapi-cloud-cli/pull/95) by [@patrick91](https://github.com/patrick91).

## 0.3.0

### Features

* ✨ Add support for `.fastapicloudignore` file. PR [#83](https://github.com/fastapilabs/fastapi-cloud-cli/pull/83) by [@patrick91](https://github.com/patrick91).

### Internal

* ⬆ Bump actions/download-artifact from 4 to 5. PR [#69](https://github.com/fastapilabs/fastapi-cloud-cli/pull/69) by [@dependabot[bot]](https://github.com/apps/dependabot).
* ⬆ Update pre-commit requirement from <4.0.0,>=2.17.0 to >=2.17.0,<5.0.0. PR [#28](https://github.com/fastapilabs/fastapi-cloud-cli/pull/28) by [@dependabot[bot]](https://github.com/apps/dependabot).
* ⬆ Bump ruff from 0.12.0 to 0.13.0. PR [#77](https://github.com/fastapilabs/fastapi-cloud-cli/pull/77) by [@dependabot[bot]](https://github.com/apps/dependabot).
* ⬆ Bump pypa/gh-action-pypi-publish from 1.9.0 to 1.13.0. PR [#73](https://github.com/fastapilabs/fastapi-cloud-cli/pull/73) by [@dependabot[bot]](https://github.com/apps/dependabot).
* ⬆ Bump actions/labeler from 5 to 6. PR [#72](https://github.com/fastapilabs/fastapi-cloud-cli/pull/72) by [@dependabot[bot]](https://github.com/apps/dependabot).
* ⬆ Bump actions/checkout from 4 to 5. PR [#68](https://github.com/fastapilabs/fastapi-cloud-cli/pull/68) by [@dependabot[bot]](https://github.com/apps/dependabot).
* ⬆ Bump tiangolo/latest-changes from 0.3.1 to 0.4.0. PR [#70](https://github.com/fastapilabs/fastapi-cloud-cli/pull/70) by [@dependabot[bot]](https://github.com/apps/dependabot).

## 0.2.1

### Features

* ✨ Add support for verification statuses. PR [#82](https://github.com/fastapilabs/fastapi-cloud-cli/pull/82) by [@DoctorJohn](https://github.com/DoctorJohn).

## 0.2.0

### Features

* ✨ Add unlink command to delete local FastAPI Cloud configuration. PR [#80](https://github.com/fastapilabs/fastapi-cloud-cli/pull/80) by [@alejsdev](https://github.com/alejsdev).
* ✨ Add support for granular failure statuses. PR [#75](https://github.com/fastapilabs/fastapi-cloud-cli/pull/75) by [@DoctorJohn](https://github.com/DoctorJohn).

## 0.1.5

### Features

* 🧑‍💻 Handle HTTP errors when streaming build logs. PR [#65](https://github.com/fastapilabs/fastapi-cloud-cli/pull/65) by [@patrick91](https://github.com/patrick91).

### Refactors

* ♻️ Prompt user for login or waitlist option when not logged in. PR [#81](https://github.com/fastapilabs/fastapi-cloud-cli/pull/81) by [@alejsdev](https://github.com/alejsdev).
* ✅ Fix mocks in tests . PR [#78](https://github.com/fastapilabs/fastapi-cloud-cli/pull/78) by [@alejsdev](https://github.com/alejsdev).

## 0.1.4

### Fixes

* 🐛 Always load settings lazily. PR [#64](https://github.com/fastapilabs/fastapi-cloud-cli/pull/64) by [@patrick91](https://github.com/patrick91).

## 0.1.3

### Fixes

* 🐛 Remove redundant thank you message. PR [#63](https://github.com/fastapilabs/fastapi-cloud-cli/pull/63) by [@patrick91](https://github.com/patrick91).

### Refactors

* ✅ Refactor tests. PR [#62](https://github.com/fastapilabs/fastapi-cloud-cli/pull/62) by [@patrick91](https://github.com/patrick91).

### Upgrades

* ⬆️  Relax httpx dependency. PR [#61](https://github.com/fastapilabs/fastapi-cloud-cli/pull/61) by [@patrick91](https://github.com/patrick91).

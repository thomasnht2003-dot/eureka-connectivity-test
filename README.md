# Eureka connectivity test (throw-away repository)

Phase 8.2, test 1. This repository exists only to find out whether NSO, VBMA and the PMI provider's public health endpoint answer a **GitHub-hosted runner**.

* Contains two public-URL files (`connectivity_targets.json`, `connectivity_test.py`) and one workflow. **No project data, no credentials, no secrets.**
* Honest user agent, robots.txt respected, one request every 2 seconds, only listing pages and the first 2 KB of two files, a refusal is never retried or worked around.
* Run it: Actions tab → `connectivity-test` → **Run workflow**. It also runs 4 times a day and stops by itself 4 days after the first run.
* Read the result in the run's **Summary** (one table). Pass = every target `OK` in every run.
* Delete the repository when the test is finished.

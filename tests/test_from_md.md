---
type: generate_code
subtype: bash_script
format: bash
timeout: 120
---
Write a bash script called health_check.sh that:
1. Accepts a HOST and PORT as arguments (with defaults: HOST=localhost, PORT=8080)
2. Uses curl to check if the HTTP endpoint is reachable (timeout 5s)
3. Prints "OK: <host>:<port> is reachable" on success
4. Prints "FAIL: <host>:<port> is unreachable" on failure
5. Exits with code 0 on success, 1 on failure

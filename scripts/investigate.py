import os sys json requests 
from openai import OpenAI

def investigate_logs(log_file_path):
    # READ LOGS FROM FILE
    if not os.path.exists(log_file_path):
        return "File does not exist"
    with open(log_file_path, 'r') as file:
        logs = file.readlines()
        tail_logs = "".join(logs[-100:])

    #2 ASK AI TO INVESTIGATE
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    prompt = f"""
    You are a senior DevOps engineer assisting with CI/CD incident triage.

    Given the following CI job logs, perform a failure analysis with the goal of minimizing investigation time for the on-call engineer.

    Your tasks:

    1. Identify the earliest real failure in the logs.
    - Ignore secondary or cascading errors that occur after the initial failure.
    - If multiple errors appear, select the one that first caused the job to fail.

    2. Precisely locate where the failure occurred.
    - Include:
        - CI job name or step (if inferable)
        - Command or script being executed
        - File path, line number, container, or pod name (if present)
    - If location is ambiguous, explain why.

    3. Categorize the failure into exactly one of the following:
    - infra
    - dependency
    - auth
    - config
   - test
   - timeout

    4. Summarize the likely root cause in 1–2 concise sentences.
    - Focus on the underlying issue, not the symptom.

    5. Provide 2–4 concrete next verification or remediation steps.
    - Steps must be actionable (specific commands, config checks, or logs to inspect).
    - Prioritize steps that confirm or rule out the root cause quickly.

    6. Format the final output exactly as a Slack-ready incident notification.

    Slack message format:

    ---
    🚨 *CI Pipeline Failure Detected*

    *Failure Category:* <category>

    *Earliest Failure:*
    <short error message>

    *Location:*
    - Job/Step: <job or step name>
    - Command: <command if available>
    - File/Path/Pod: <file path, container, or pod name if available>

    *Likely Root Cause:*
    <concise explanation>

    *Recommended Next Steps:*
    1. <step one>
    2. <step two>
    3. <step three (if applicable)>
    ---

    Logs:
    {tail_logs}

    Do not include raw logs.
    Do not speculate beyond the evidence in the logs.
    If required information is missing, explicitly state what is missing.
    """
    response = client.chat.completions.create(
        model="gpt-5-nano",
        messages=[
            {"role": "system", "content": "You are a senior DevOps engineer assisting with CI/CD incident triage."},
            {"role": "user", "content": prompt}
        ]
    )
    return response.choices[0].message.content

    def send_to_slack(message):
        # Send Report to Slack
        slack_webhook_url = os.getenv("SLACK_WEBHOOK")
        if not slack_webhook_url:
            raise ValueError("SLACK_WEBHOOK environment variable is not set")
        payload = {
            "text": f"🚨 *CI/CD Failure Analysis* 🚨\n{message}"
        }
        requests.post(slack_webhook_url, json=payload)
if __name__ == "__main__":
    log_file_path = sys.argv[1]
    report = investigate_logs(log_file_path)
    send_to_slack(report)
    print("Analysis completed. Report sent to Slack.")
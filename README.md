# KDCA weekly report KakaoTalk notifier

Every Friday at 08:30, this checks the KDCA infectious disease portal for the latest `감염병 표본감시 주간소식지`. If a new report is found, it sends a KakaoTalk message to your own chat.

## Files

- `kdca_kakao_report.py`: checks the latest report and sends KakaoTalk
- `kakao_oauth_setup.py`: one-time Kakao refresh token helper
- `config.example.json`: sample configuration
- `register_weekly_task.ps1`: Windows Task Scheduler registration script
- `state.json`: last-sent report record, created automatically after first send

## Setup

1. Copy `config.example.json` to `config.json`.
2. Create a Kakao Developers app and put its REST API key in `kakao_rest_api_key`.
3. Enable Kakao Login and the `talk_message` consent item.
4. Register this Redirect URI in Kakao Developers: `http://localhost:8765/callback`.
5. Run the one-time OAuth helper.

```powershell
python "D:\감영병 모니터링\kakao_oauth_setup.py"
```

Open the Kakao authorization URL printed by the helper. After consent, `config.json` will be updated with Kakao tokens.

`verify_ssl` is set to `false` in the sample config because this PC's Python certificate store failed HTTPS verification during testing. You can switch it to `true` after fixing local Python certificates.

## Test

Check the latest report without sending KakaoTalk.

```powershell
python "D:\감영병 모니터링\kdca_kakao_report.py" --dry-run
```

Send a test KakaoTalk message even if the latest report was already sent.

```powershell
python "D:\감영병 모니터링\kdca_kakao_report.py" --force
```

## Register Friday 08:30 Schedule

Run this in PowerShell.

```powershell
powershell -ExecutionPolicy Bypass -File "D:\감영병 모니터링\register_weekly_task.ps1"
```

This registers a Windows scheduled task named `KDCA Weekly Infectious Disease Kakao Report`.

## Railway

Railway Cron uses UTC. Friday 08:30 KST is Thursday 23:30 UTC, so use this cron expression:

```text
30 23 * * 4
```

Add these Railway Variables:

```text
KAKAO_REST_API_KEY=your_rest_api_key
KAKAO_REFRESH_TOKEN=your_refresh_token
VERIFY_SSL=false
DISABLE_STATE=true
```

Optional variables:

```text
KAKAO_CLIENT_SECRET=your_client_secret
FORCE_SEND=true
```

The Railway start command is defined in `railway.json`:

```text
python kdca_kakao_report.py
```

# Sprint95-2A

- Dashboard standard binding restored to `127.0.0.1`
- LAN/Firewall workflow removed from the supported default path
- Mobile layout retained at `/mobile`
- Root README updated through Sprint95-2A

## Test

```powershell
pytest `
  tests/test_dashboard_mobile_page.py `
  tests/test_dashboard_mobile_launcher.py `
  tests/test_dashboard_strategy_service.py `
  tests/test_dashboard_strategy_web_api.py `
  tests/test_dashboard_web_app.py `
  tests/test_dashboard_launcher.py -q
```

## Git

```powershell
git add .
git commit -m "Sprint95-2A: extend dashboard and restore local-only access"
git push origin main
```

"""End-to-end browser walkthrough of the trial web app (plan 2026-11-05-trial-acceptance-and-monitor, Task 5).

It drives the real UI through NGINX with the system Chrome (Playwright channel "chrome"), as the test
accounts in .env (MARK_TEST_ENGINEER_* / MARK_TEST_ADMIN_*):

  login -> dashboard (ELR table) -> search ELR -> preview (ABS image, Oracle grid)
  -> Approve is blocked while ERROR lines are unreviewed -> review each ERROR line -> Approve
  -> admin page shows review.saved / approval.saved

Writes: the review and approval rows it creates (user qa_engineer, run --run) are deleted at the end
(audit_log rows are kept as evidence). Use --keep to leave them.

Output: one line per step "OK <step> ..." / "FAIL <step> <reason>"; never prints passwords, mark values,
SLR text or image paths. Screenshots go to --out (git-ignored reports/), and contain customer data:
keep them on internal machines only.

Exit code: 0 when every step passes, 1 otherwise.
"""
import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "services" / "api"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from mark_engine.adapters.env import load_env  # noqa: E402

RESULTS: list[tuple[bool, str, str]] = []


def step(name: str, ok: bool, info: str = "") -> bool:
    RESULTS.append((ok, name, info))
    print(f"{'OK  ' if ok else 'FAIL'} {name} {info}".rstrip(), flush=True)
    return ok


def pick_elr(api, run: int) -> tuple[str, list[int]] | None:
    """First ERROR ELR (not HOLD, image available, no decision yet, <= 3 ERROR lines)."""
    page = 1
    while page <= 20:
        r = api.get(f"/api/elrs?run={run}&result=ERROR&page={page}")
        if not r.ok:
            return None
        rows = r.json()["rows"]
        if not rows:
            return None
        for row in rows:
            d = api.get(f"/api/elrs/{row['elr_no']}?run={run}")
            if not d.ok:
                continue
            det = d.json()
            if det.get("approval") or not det.get("image_available"):
                continue
            if (det.get("job") or {}).get("processing_status") == "HOLD":
                continue
            err = [l["line_no"] for l in det["lines"] if l["group"] == "ERROR"]
            if 1 <= len(err) <= 3:
                return row["elr_no"], err
        page += 1
    return None


def login(page, base: str, user: str, pw: str) -> bool:
    page.goto(f"{base}/login")
    page.fill("input[type=text]", user)
    page.fill("input[type=password]", pw)
    with page.expect_response(lambda r: r.url.endswith("/api/auth/login")) as resp:
        page.click("button[type=submit]")
    if resp.value.status != 200:
        return False
    page.wait_for_url(f"{base}/", timeout=10000)
    return True


def cleanup(run: int, username: str, since: datetime) -> str:
    import psycopg2
    conn = psycopg2.connect(host=os.getenv("MARK_PG_HOST", "10.151.28.2"), dbname=os.getenv("MARK_PG_DB", "mark_web"),
                            user=os.getenv("MARK_PG_USER", "postgres"), password=os.environ["MARK_PG_PASSWORD"],
                            connect_timeout=8)
    try:
        with conn.cursor() as cur:
            cur.execute("select user_id from mark_app.app_user where lower(username) = %s", (username.lower(),))
            uid = cur.fetchone()[0]
            cur.execute("delete from mark_app.approval where user_id = %s and run_id = %s and created_at >= %s",
                        (uid, run, since))
            n_app = cur.rowcount
            cur.execute("delete from mark_app.line_review where reviewer_id = %s and run_id = %s and created_at >= %s",
                        (uid, run, since))
            n_rev = cur.rowcount
        conn.commit()
        return f"deleted {n_rev} review(s), {n_app} approval(s) by {username}; audit_log kept"
    finally:
        conn.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", default="http://localhost:8088")
    ap.add_argument("--run", type=int, default=19)
    ap.add_argument("--env-file", default=str(ROOT / ".env"))
    ap.add_argument("--out", default=str(ROOT / "reports" / "e2e"))
    ap.add_argument("--keep", action="store_true", help="keep the review/approval rows created by the test")
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()

    load_env(Path(args.env_file))
    need = ["MARK_TEST_ENGINEER_USER", "MARK_TEST_ENGINEER_PASSWORD", "MARK_TEST_ADMIN_USER", "MARK_TEST_ADMIN_PASSWORD"]
    missing = [k for k in need if not os.getenv(k)]
    if missing:
        step("env", False, "missing " + ", ".join(missing))
        return 1
    eng_u, eng_p = os.environ["MARK_TEST_ENGINEER_USER"], os.environ["MARK_TEST_ENGINEER_PASSWORD"]
    adm_u, adm_p = os.environ["MARK_TEST_ADMIN_USER"], os.environ["MARK_TEST_ADMIN_PASSWORD"]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    base, run = args.base.rstrip("/"), args.run
    started = datetime.now(timezone.utc)
    wrote = False

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=not args.headed)
        try:
            ctx = browser.new_context(base_url=base, viewport={"width": 1440, "height": 900})
            page = ctx.new_page()

            # 1. Login as engineer
            if not step("login_engineer", login(page, base, eng_u, eng_p)):
                return 1

            # 2. Dashboard: cards + ELR table (real ELR rows, not the loading/empty row), no load-error banner
            try:  # wait until the table has left its loading state and shows real rows (expect a full page of 50)
                page.wait_for_function(
                    "() => !document.body.innerText.includes('Loading records') && document.querySelectorAll('tbody tr').length >= 2",
                    timeout=20000)
            except Exception:
                pass
            page.screenshot(path=str(out / "01_dashboard.png"), full_page=True)
            body = page.inner_text("body")
            rows = page.locator("tbody tr").count()
            step("dashboard", "ไม่สำเร็จ" not in body and rows >= 1 and "No ELR" not in body, f"ELR rows on page 1={rows}")

            # 3. Pick an ELR through the same session's API, then find it with the search box
            picked = pick_elr(ctx.request, run)
            if not step("pick_elr", picked is not None, f"error_lines={len(picked[1]) if picked else 0}"):
                return 1
            elr, err_lines = picked
            page.fill("input[placeholder^='Search ELR']", elr)
            page.wait_for_selector(f"tbody tr:has-text('{elr}')", timeout=10000)
            page.click(f"tbody tr:has-text('{elr}')")
            page.wait_for_url(f"**/elr/{elr}?run={run}", timeout=10000)
            step("search_and_open", True, elr)

            # 4. Preview: ABS image decoded, Oracle grid shown
            page.wait_for_selector("text=Oracle Actual ACTIVEL", timeout=15000)
            try:  # wait for the ABS image to finish decoding (it can arrive after the grid)
                page.wait_for_function("() => [...document.images].some(i => i.complete && i.naturalWidth > 0 && i.src.includes('/api/files/abs/'))", timeout=15000)
                img_ok = True
            except Exception:
                img_ok = False
            step("preview", img_ok, "ABS image loaded, Oracle grid shown" if img_ok else "ABS image not loaded")
            page.screenshot(path=str(out / "02_preview.png"), full_page=True)

            # 5. Approve must be blocked while ERROR lines have no reason + corrected mark
            with page.expect_response(lambda r: r.url.endswith("/api/approvals")) as r_block:
                page.click("button:has-text('Approve')")
            page.wait_for_selector("text=ไม่สามารถ Approve ได้", timeout=5000)
            step("approve_blocked", r_block.value.status in (409, 422), f"status={r_block.value.status}")

            # 6. Review every ERROR line (reason OTHER, corrected mark = system expected, note marks the test)
            detail = ctx.request.get(f"/api/elrs/{elr}?run={run}").json()
            expected = {l["line_no"]: l["expected"] or "-" for l in detail["lines"]}
            for n in err_lines:
                # innermost review card for this line (outer panels also contain the text, so take the last match)
                form = page.locator("div.rounded-lg.overflow-hidden.text-xs", has=page.locator(f"span:text-is('Line {n}')")).last
                form.locator(f"span:text-is('Line {n}')").wait_for(state="visible", timeout=15000)
                if not form.locator("select").is_visible():   # ERROR lines open by default; expand only if collapsed
                    form.locator(f"span:text-is('Line {n}')").click()
                form.locator("select").select_option("OTHER")
                form.locator("input[placeholder='Enter approved mark']").fill(expected[n])
                form.locator("input[placeholder^='Investigation note']").fill("E2E walkthrough test (auto cleanup)")
                with page.expect_response(lambda r: r.url.endswith("/api/reviews")) as r_rev:
                    with page.expect_response(lambda r: f"/api/elrs/{elr}" in r.url and r.request.method == "GET", timeout=15000):
                        form.locator("button:has-text('Confirm Review')").click()   # save, then the page re-fetches detail
                page.wait_for_timeout(500)   # let the forms re-render after the re-fetch
                wrote = True
                if not step(f"review_line_{n}", r_rev.value.status == 200, f"status={r_rev.value.status}"):
                    return 1

            # 7. Approve now succeeds
            with page.expect_response(lambda r: r.url.endswith("/api/approvals")) as r_app:
                page.click("button:has-text('Approve')")
            page.wait_for_selector("text=Current: APPROVED", timeout=10000)
            step("approve", r_app.value.status == 200, f"status={r_app.value.status}")
            page.screenshot(path=str(out / "03_approved.png"), full_page=True)

            # 8. Admin sees the events
            actx = browser.new_context(base_url=base, viewport={"width": 1440, "height": 900})
            apage = actx.new_page()
            step("login_admin", login(apage, base, adm_u, adm_p))
            apage.goto(f"{base}/admin")
            # The filter <select> also lists these action names, so read only event-table rows.
            # Events carry no ELR/run column, so match rows by the engineer's display name among the newest events.
            eng_name = ctx.request.get("/api/auth/me").json()["display_name"]
            try:
                apage.locator("tbody tr", has_text="approval.saved").first.wait_for(timeout=15000)
            except Exception:
                pass
            atext = " ".join(r for r in apage.locator("tbody tr").all_inner_texts() if eng_name in r)
            n_rev = atext.count("review.saved")
            step("admin_events", n_rev >= len(err_lines) and "approval.saved" in atext,
                 f"review.saved x{n_rev}, approval.saved {'yes' if 'approval.saved' in atext else 'no'}")
            apage.screenshot(path=str(out / "04_admin.png"), full_page=True)
        except Exception as e:  # any timeout or selector miss is a failed step, not a crash
            step("exception", False, f"{type(e).__name__}: {str(e).splitlines()[0][:160]}")
        finally:
            browser.close()
            if wrote and not args.keep:
                try:
                    step("cleanup", True, cleanup(run, eng_u, started))
                except Exception as e:
                    step("cleanup", False, f"{type(e).__name__}: {str(e).splitlines()[0][:160]}")

    failed = [n for ok, n, _ in RESULTS if not ok]
    print(f"{'PASS' if not failed else 'FAIL'}: {len(RESULTS) - len(failed)}/{len(RESULTS)} steps; screenshots in {out}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())

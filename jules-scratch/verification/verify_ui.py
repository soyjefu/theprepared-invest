import re
from playwright.sync_api import sync_playwright, Page, expect

def run(playwright):
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()

    # The Django app is running on port 8000 inside the Docker network.
    # I need to find out how this is exposed to the host. Assuming localhost:8000 for now.
    base_url = "http://localhost:8000"

    try:
        # Login
        print("Navigating to login page...")
        page.goto(f"{base_url}/admin/login/?next=/")
        page.get_by_label("Username").fill("testuser")
        page.get_by_label("Password").fill("testpassword123")
        page.get_by_role("button", name="Log in").click()

        # Verify login was successful by checking for a known element on the main site
        expect(page.get_by_role("link", name="대시보드")).to_be_visible()
        print("Login successful.")

        # Dashboard Screenshot
        print("Navigating to Dashboard...")
        page.goto(f"{base_url}/dashboard/")
        expect(page.get_by_role("heading", name="계좌 종합 현황")).to_be_visible()
        page.screenshot(path="jules-scratch/verification/dashboard.png")
        print("Dashboard screenshot captured.")

        # Portfolio Screenshot
        print("Navigating to Portfolio...")
        page.goto(f"{base_url}/portfolio/")
        expect(page.get_by_role("heading", name="계좌별 포트폴리오")).to_be_visible()
        page.screenshot(path="jules-scratch/verification/portfolio.png")
        print("Portfolio screenshot captured.")

        # System Management Screenshot
        print("Navigating to System Management...")
        page.goto(f"{base_url}/system/")
        expect(page.get_by_role("heading", name="AI 분석 기반 추천 종목")).to_be_visible()
        page.screenshot(path="jules-scratch/verification/system.png")
        print("System Management screenshot captured.")

    except Exception as e:
        print(f"An error occurred during Playwright verification: {e}")
        # Take a screenshot on error for debugging
        page.screenshot(path="jules-scratch/verification/error.png")
    finally:
        context.close()
        browser.close()

with sync_playwright() as playwright:
    run(playwright)

// Walk the app through one fake event and screenshot every step, so a change can be
// checked by eye without clicking through by hand.
//
//   node scripts/screenshots.mjs [out_dir]        (default: output/screens)
//
// Starts its own Streamlit on port 8599 with the free stub reader and a throwaway
// output folder, so it never touches your saved events. Needs Node with Playwright.
import { spawn } from "node:child_process";
import { mkdirSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { createRequire } from "node:module";
import { join, resolve } from "node:path";

// require() so a global Playwright install (NODE_PATH) is found too.
const { chromium } = createRequire(import.meta.url)("playwright");

const ROOT = resolve(import.meta.dirname, "..");
const OUT = resolve(process.argv[2] || join(ROOT, "output", "screens"));
const PORT = 8599;
mkdirSync(OUT, { recursive: true });

const app = spawn("python", ["-m", "streamlit", "run", "app.py", "--server.headless", "true",
  "--server.port", String(PORT)], {
  cwd: ROOT,
  env: { ...process.env, TALLYABLE_EXTRACTOR: "stub", TALLYABLE_OUTPUT_DIR: mkdtempSync(join(tmpdir(), "tly-")),
         APP_PASSWORD: "" },
  stdio: "ignore",
});

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
const idle = () => page.waitForFunction(() => !document.querySelector('[data-testid="stStatusWidget"]'), null,
  { timeout: 30000 }).then(() => page.waitForTimeout(600));
const shot = async (name, locator) => {
  await idle();
  const target = locator ?? page;
  await target.screenshot({ path: join(OUT, `${name}.png`), ...(locator ? {} : { fullPage: true }) });
  console.log("saved", join(OUT, `${name}.png`));
};
const step = async (label) => {
  await page.locator('[data-testid="stSidebar"] label').filter({ hasText: label }).first().click();
  await idle();
};

try {
  for (let i = 0; ; i++) {  // wait for Streamlit to come up
    try { await page.goto(`http://localhost:${PORT}`); break; } catch (e) { if (i > 60) throw e; }
    await page.waitForTimeout(500);
  }
  await page.getByText("What's your club called?").waitFor({ timeout: 60000 });
  await shot("0-club-name");
  await page.getByPlaceholder("e.g. Sunrise Hiking Club").fill("Sunrise Hiking Club");
  await page.getByPlaceholder("e.g. Sunrise Hiking Club").press("Enter");
  await idle();
  const startBalance = page.getByPlaceholder("0.00").first();
  await startBalance.fill("1000");
  await startBalance.press("Enter");
  await idle();
  await shot("0-club-home-empty");
  await page.getByRole("button", { name: "New event" }).click();
  await page.getByText("Start a new event").waitFor({ timeout: 60000 });
  await shot("0-start-empty");
  for (const name of ["Jamie Lee", "Sam Park"]) {  // Continue waits for at least one member
    await page.getByPlaceholder("e.g. Jamie Lee").fill(name);
    await page.getByPlaceholder("e.g. Jamie Lee").press("Enter");
    await idle();
  }
  await shot("0-start-ready");
  await page.getByRole("button", { name: /Continue to receipts/ }).click();
  await page.getByText("Use the fake event's 14 receipts instead").waitFor({ timeout: 60000 });
  await shot("1-upload-empty");
  await page.getByRole("button", { name: "Use the fake event's 14 receipts instead" }).click();
  await idle();
  await page.getByRole("button", { name: "Apply to all" }).click();
  await idle();
  await page.getByRole("button", { name: "Draft rows" }).click();
  await page.getByRole("button", { name: /Go to Review/ }).waitFor({ timeout: 60000 });
  await shot("1-upload-drafted");

  await step("Review");
  await shot("2-review");
  for (const rid of ["R06", "R09"]) {  // R06 has a math error, R09 a returned item
    await page.locator('[data-testid="stSidebar"] label').filter({ hasText: rid }).first().click();
    await idle();
    await shot(`2-review-${rid}`);
    const flags = page.locator('[class*="st-key-flag-"]');
    for (let n = 0; n < await flags.count(); n++) await shot(`2-review-${rid}-flag-${n}`, flags.nth(n));
  }

  // Leave out R11, the planted duplicate: the button waits for a reason.
  await page.locator('[data-testid="stSidebar"] label').filter({ hasText: "R11" }).first().click();
  await idle();
  const note = page.getByPlaceholder(/Why you're approving/);
  await note.fill("Duplicate of R03, same place, date and total");
  await note.press("Enter");
  await idle();
  await page.getByRole("button", { name: "Leave out" }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: join(OUT, "2-review-R11-note.png") });
  await page.getByRole("button", { name: "Leave out" }).click();
  await idle();
  await page.locator('[data-testid="stSidebar"] label').filter({ hasText: "R11" }).first().click();
  await idle();
  await shot("2-review-R11-left-out");

  await page.getByRole("button", { name: /Approve the \d+ with no flags/ }).click();
  await idle();
  for (let n = 0; n < 15; n++) {  // approve the flagged ones too, with a note, so Push opens up
    const left = page.locator('[data-testid="stSidebar"] label').filter({ hasText: "⏳" });
    if (!(await left.count())) break;
    await left.first().click();
    await idle();
    const why = page.getByPlaceholder(/Why you're approving/);
    await why.fill("Checked against the photo");
    await why.press("Enter");
    await idle();
    await page.getByRole("button", { name: "Approve", exact: true }).click();
    await idle();
  }
  await step("Summary");
  const firstAmount = page.locator('.st-key-income-box input[placeholder="0.00"]').first();
  await firstAmount.fill("500");
  await firstAmount.press("Enter");
  await shot("3-summary");
  const panel = page.locator(".tly-money").first();
  await shot("3-summary-money", panel);
  await page.getByRole("button", { name: /Push to/ }).click();
  await page.locator(".st-key-books-in").waitFor({ timeout: 60000 });
  await shot("3-summary-done-card", page.locator(".st-key-books-in"));
  await firstAmount.fill("520");  // an edit after Push: the card asks to push again
  await firstAmount.press("Enter");
  await page.locator(".st-key-push-stale").waitFor({ timeout: 30000 });
  await shot("3-summary-stale", page.locator(".st-key-push-stale"));
  await page.getByRole("button", { name: "Push again" }).click();
  await page.locator(".st-key-books-in").waitFor({ timeout: 60000 });

  await step("Close out");
  await page.getByRole("heading", { name: "Who's owed" }).hover();  // header link icon must stay hidden
  await shot("4-close-out");
  await shot("4-whos-owed", page.locator(".st-key-whos-owed"));
  await page.getByText(/Left out of the books/).click();
  await shot("4-close-out-left-out");
  await page.getByRole("button", { name: "Mark paid" }).first().click();
  await idle();
  await shot("4-close-out-undo", page.locator(".st-key-whos-owed"));
  await page.getByRole("combobox", { name: /^Funder/ }).scrollIntoViewIfNeeded();
  await page.getByRole("combobox", { name: /^Funder/ }).click();
  await page.waitForTimeout(500);
  await page.screenshot({ path: join(OUT, "4-close-out-funders.png") });
  await page.keyboard.press("Escape");
  await shot("4-close-out-finish-button", page.locator(".st-key-finish-row"));
  await page.getByRole("button", { name: "Finish event" }).click();
  await page.locator(".tly-confetti").waitFor({ timeout: 30000 });  // added last, once the page is built
  await page.waitForTimeout(1400);
  await page.screenshot({ path: join(OUT, "5-finish-confetti.png") });  // mid-fall, so no idle wait
  await page.waitForTimeout(4500);
  await shot("5-finish");
  await shot("5-finish-card", page.locator(".st-key-finish-page"));
  await page.getByText(/Past events/).click();
  await shot("5-finish-sidebar", page.locator('[data-testid="stSidebar"]'));
  const clubMenu = page.locator('.st-key-club-menu [data-testid="stPopoverButton"]');
  await clubMenu.click();
  await page.waitForTimeout(500);
  await page.screenshot({ path: join(OUT, "7-club-menu.png") });
  await page.getByRole("button", { name: "Club home", exact: true }).click();
  await idle();
  await shot("7-club-home");
  await clubMenu.click();
  await page.getByPlaceholder("New club name").fill("Chess & Coffee");
  await page.getByPlaceholder("New club name").press("Enter");
  await idle();
  await shot("7-club-home-new-club");
  await page.goto(`http://localhost:${PORT}`);  // a new tab with two clubs asks which one
  await page.getByText("Which club are you doing the books for?").waitFor({ timeout: 60000 });
  await shot("8-which-club");
  await page.getByRole("button", { name: "Open Sunrise Hiking Club" }).click();
  await idle();
  await page.locator('[data-testid="stSidebarCollapseButton"] button').click();
  await page.waitForTimeout(800);
  await page.screenshot({ path: join(OUT, "6-sidebar-collapsed.png") });
} finally {
  await browser.close();
  app.kill();
}

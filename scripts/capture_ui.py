"""Verify the running screen and regenerate product screenshots using Playwright."""

import argparse
import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--base-url", default="http://localhost:3000")
parser.add_argument("--docs-url", default="http://localhost:3002")
parser.add_argument("--storage-state", type=Path, help="Playwright sign-in state for a screenshot account")
parser.add_argument("--output", type=Path, default=ROOT / "screenshots")
args = parser.parse_args()
BASE = args.base_url.rstrip("/")
OUTPUT = args.output / "ui-review"
DOCS = args.docs_url.rstrip("/")


def url(path):
    return path if path.startswith("http") else BASE + path


async def prepare(page, name):
    await page.evaluate("document.fonts.ready")
    if name == "landing":
        await page.locator(".harbor-viewport[data-ready=true]").wait_for(timeout=20000)
        pause = page.get_by_role("button", name="Pause harbor animation", exact=True)
        if await pause.count():
            await pause.click()
        await page.get_by_role("button", name="Pause feature cards", exact=True).click()
        await page.evaluate("window.scrollTo(0, 0)")
        await page.evaluate("new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(() => requestAnimationFrame(resolve))))")


async def check_alignment(page, name):
    if name == "landing":
        assert await page.locator(".bento-memory").evaluate("el => getComputedStyle(el).color") != "rgb(255, 255, 255)", "unreadable light memory card"
    if name == "dashboard":
        rows = await page.locator(".activity-row").evaluate_all("""rows => rows.map(row => {
            const icon = row.querySelector('.activity-icon').getBoundingClientRect();
            const description = row.querySelector('.activity-description').getBoundingClientRect();
            const meta = row.querySelector('.activity-meta').getBoundingClientRect();
            const style = getComputedStyle(row.querySelector('.activity-description'));
            return {left: description.left, meta: meta.left,
                iconCenter: icon.top + icon.height / 2,
                textCenter: description.top + parseFloat(style.paddingTop) + parseFloat(style.lineHeight) / 2};
        })""")
        for row in rows:
            assert abs(row["left"] - row["meta"]) < 1, (name, "activity metadata indentation", row)
            assert abs(row["iconCenter"] - row["textCenter"]) < 1, (name, "activity icon alignment", row)
        if rows:
            assert max(row["left"] for row in rows) - min(row["left"] for row in rows) < 1
    if name == "ports":
        bounds = await page.get_by_label("Filter listed ports").bounding_box()
        assert bounds["width"] >= 200, (name, "search field collapsed", bounds)
    if name == "episodes":
        for time in await page.locator("tbody time").all():
            assert await time.evaluate("el => el.getClientRects().length") == 1, "date split across lines"
    if name == "agents":
        rows = await page.locator(".agent-card").evaluate_all("""cards => cards.map(card => ({
          row: Math.round(card.getBoundingClientRect().top),
          note: card.querySelector('.agent-note').getBoundingClientRect().top
        }))""")
        for row in {card["row"] for card in rows}:
            notes = [card["note"] for card in rows if card["row"] == row]
            assert max(notes) - min(notes) < 2, (name, "card footers misaligned", notes)
    if name == "chat":
        selector = page.get_by_label("Assistant model", exact=True)
        if await selector.count():
            assert await selector.locator("option").count() >= 1
            assert await selector.evaluate("el => el.getBoundingClientRect().right <= innerWidth"), "model selector overflow"
        suggestions = page.locator("button.button-quiet")
        if await suggestions.count():
            background = await suggestions.first.evaluate("el => getComputedStyle(el).backgroundColor")
            assert background == "rgba(0, 0, 0, 0)", "suggestion inherits dark primary-button background"
            widths = [box["width"] for box in [await item.bounding_box() for item in await suggestions.all()]]
            assert max(widths) - min(widths) < 2, "suggestion cards have uneven column widths"
    for heading in await page.locator(".card-heading").all():
        assert await heading.evaluate("""el => {
          const title = el.querySelector('h2').getBoundingClientRect();
          const meta = el.querySelector('.card-meta')?.getBoundingClientRect();
          return !meta || title.right <= meta.left + 1 || title.bottom <= meta.top + 1;
        }"""), (name, "card title overlaps metadata")


async def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        page = await browser.new_page(
            viewport={"width": 1440, "height": 1000}, device_scale_factor=1,
            storage_state=str(args.storage_state) if args.storage_state else None
        )
        await page.add_init_script("""const getContext = HTMLCanvasElement.prototype.getContext;
        HTMLCanvasElement.prototype.getContext = function(type, options, ...rest) {
         return getContext.call(this, type, type.includes('webgl') ? {...options, preserveDrawingBuffer: true} : options, ...rest);
        };""")
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        routes = {
            "landing": "/",
            "dashboard": "/dashboard",
            "sources": "/sources",
            "agents": "/agents",
            "investigate": "/investigate",
            "ports": "/ports?country=IND",
            "berths": "/berths",
            "episodes": "/episodes?state=open",
            "learned": "/learned",
            "desk": "/desk",
            "profile": "/profile",
            "chat": "/desk/chat",
            "search": "/search?q=Helsinki&kind=Port",
            "docs": DOCS + "/",
        }
        for name, path in routes.items():
            response = await page.goto(url(path), wait_until="networkidle")
            assert response.status == 200, (path, response.status)
            assert "/login" not in page.url, "Use --storage-state with a signed-in screenshot account."
            assert await page.locator("h1").count() == 1, (path, "missing title")
            text = await page.locator("body").inner_text()
            assert "This page could not be shown" not in text, (path, "error boundary")
            assert "Nothing here by that name" not in text, (path, "404 boundary")
            assert not await page.evaluate(
                "document.documentElement.scrollWidth > innerWidth"
            ), (path, "horizontal overflow")
            await prepare(page, name)
            await check_alignment(page, name)
            await page.screenshot(
                path=str(OUTPUT / f"{name}-desktop.png"),
                full_page=name in {"landing", "dashboard", "sources"},
            )
            print("desktop OK", path, flush=True)

        await page.goto(BASE + "/", wait_until="networkidle")
        await prepare(page, "landing")
        await page.get_by_role("button", name="Follow vessel", exact=True).click()
        assert await page.get_by_role("button", name="Show harbor", exact=True).get_attribute("aria-pressed") == "true"
        await page.get_by_role("button", name="Show shipping route", exact=True).click()
        assert await page.get_by_role("button", name="Show shipping route", exact=True).get_attribute("aria-pressed") == "false"
        await page.get_by_role("button", name="Reset harbor view", exact=True).click()
        await page.get_by_role("button", name="Semantic", exact=True).click()
        assert await page.locator(".memory-layer[aria-hidden=false] strong").inner_text() == "Lessons with receipts."
        await page.get_by_role("button", name="Berth", exact=True).click()
        assert "Berth assignments" in await page.locator(".diagram-caption").inner_text()
        await page.locator(".crew-cards").hover()
        await page.get_by_role("button", name="Watcher Spot the overlap 01", exact=True).click()
        assert "highest overlap" in await page.locator(".crew-explanation").inner_text()
        reduced = await browser.new_page(reduced_motion="reduce")
        await reduced.goto(BASE + "/", wait_until="networkidle")
        await reduced.locator(".harbor-viewport[data-ready=true]").wait_for()
        assert await reduced.locator(".memory-tape-track").evaluate("el => getComputedStyle(el).animationName") == "none"
        await reduced.close()
        fallback = await browser.new_page()
        await fallback.add_init_script("""const original = HTMLCanvasElement.prototype.getContext;
            HTMLCanvasElement.prototype.getContext = function(type, ...args) {
                return type.includes('webgl') ? null : original.call(this, type, ...args);
            };""")
        await fallback.goto(BASE + "/", wait_until="networkidle")
        await fallback.get_by_text("Maritime illustration", exact=True).wait_for()
        assert await fallback.locator(".harbor-controls").count() == 0
        assert await fallback.locator(".harbor-fallback").is_visible()
        await fallback.close()
        print("Three.js controls, bento cards, reduced motion and WebGL fallback OK", flush=True)

        await page.goto(BASE + "/ports", wait_until="networkidle")
        await page.locator(".ops-map-context > summary").click()
        chart = page.locator("svg.map")
        original = await chart.get_attribute("viewBox")
        await page.get_by_label("Map region", exact=True).select_option("Asia")
        assert await chart.get_attribute("viewBox") != original
        before_zoom = await chart.get_attribute("viewBox")
        await page.get_by_role("button", name="Zoom in", exact=True).click()
        assert await chart.get_attribute("viewBox") != before_zoom
        await page.get_by_role("button", name="Reset map").click()
        assert await chart.get_attribute("viewBox") == original
        all_ports = await chart.locator("a").count()
        await page.get_by_label("Show only unusual ports on the map", exact=True).check()
        assert 0 < await chart.locator("a").count() < all_ports
        await chart.locator("a").first.focus()
        await page.keyboard.press("Enter")
        details = page.get_by_role("link", name="Port details", exact=True)
        await details.wait_for()
        await page.screenshot(path=str(OUTPUT / "map-selected-desktop.png"))
        await details.click()
        await page.wait_for_url("**/ports/**")
        await page.wait_for_load_state("networkidle")
        assert "/ports/" in page.url
        selected_port = page.url.removeprefix(BASE)
        assert (
            "Nothing here by that name" not in await page.locator("body").inner_text()
        )
        print("map controls, keyboard selection, detail navigation OK", flush=True)

        await page.goto(BASE + "/berths", wait_until="networkidle")
        all_berths = await page.locator("tbody tr").count()
        await page.get_by_role("button", name="Overload signals").click()
        assert 0 < await page.locator("tbody tr").count() < all_berths
        await page.get_by_label("Filter berths").fill("NO_SUCH_BERTH_12345")
        assert await page.locator("tbody tr").count() == 0
        await page.get_by_label("Filter berths").fill("")
        await page.get_by_role("button", name="All berths").click()
        assert await page.locator("tbody tr").count() == all_berths
        await page.locator("tbody tr a").first.click()
        await page.wait_for_url("**/berths/**")
        await page.wait_for_load_state("networkidle")
        assert "/berths/" in page.url
        assert (
            "Nothing here by that name" not in await page.locator("body").inner_text()
        )
        print("berth filters and detail navigation OK", flush=True)

        await page.goto(BASE + "/ports?country=IND", wait_until="networkidle")
        await page.get_by_label("Filter listed ports").fill("NO_SUCH_PORT_12345")
        assert await page.locator("tbody tr").count() == 0
        await page.get_by_label("Filter listed ports").fill("")
        await page.get_by_label("Sort listed ports").select_option("name")
        names = await page.locator("tbody tr td:first-child a").all_text_contents()
        assert len(names) > 2
        await page.get_by_label("Country", exact=True).select_option("FIN")
        await page.get_by_role("button", name="Show", exact=True).click()
        await page.wait_for_url("**/ports?country=FIN")
        await page.wait_for_load_state("networkidle")
        assert "country=FIN" in page.url
        print("port filters, sorting, country submission OK", flush=True)

        for width in [360, 390, 768, 1024]:
            await page.set_viewport_size(
                {"width": width, "height": 844 if width == 390 else 1024}
            )
            for name in [
                "landing",
                "dashboard",
                "sources",
                "agents",
                "investigate",
                "docs",
                "ports",
                "berths",
                "episodes",
                "learned",
                "desk",
                "chat",
                "search",
            ]:
                await page.goto(url(routes[name]), wait_until="networkidle")
                assert not await page.evaluate(
                    "document.documentElement.scrollWidth > innerWidth"
                ), (name, width, "horizontal overflow")
                await prepare(page, name)
                await check_alignment(page, name)
                await page.screenshot(
                    path=str(OUTPUT / f"{name}-{width}.png"),
                    full_page=name in {"landing", "dashboard", "sources"},
                )
                print(f"{width}px OK", name, flush=True)
            if width == 390:
                await page.goto(BASE + "/dashboard", wait_until="networkidle")
                menu = page.locator("aside details")
                await menu.locator("summary").click()
                await menu.get_by_role("link", name="Data sources", exact=True).click()
                await page.wait_for_url("**/sources")
                await page.get_by_role("button", name="Refresh workspace").click()
                assert (
                    await page.get_by_role("heading", name="Know your sources").count()
                    == 1
                )
                print("mobile navigation and refresh OK", flush=True)
        await page.set_viewport_size({"width": 1440, "height": 1000})
        await page.goto(BASE + "/investigate", wait_until="networkidle")
        nodes = page.locator("svg[aria-label^='Interactive'] [role=button]")
        assert await nodes.count() > 1
        await nodes.last.focus()
        await page.keyboard.press("Enter")
        assert (
            await page.get_by_role("link", name="Explore this node", exact=True).count()
            == 1
        )
        await page.screenshot(path=str(OUTPUT / "graph-selected-desktop.png"))
        calls = page.locator("svg[aria-label^='Interactive'] [role=button][aria-label^='Inspect PortCall']")
        assert await calls.count() > 1, "need connected port calls to exercise tracing"
        await calls.first.click()
        await page.get_by_role("button", name="Use as start", exact=True).click()
        await calls.last.click()
        await page.get_by_role("button", name="Use as destination", exact=True).click()
        await page.get_by_role("button", name="Trace path", exact=True).click()
        await page.wait_for_url("**/investigate?**from_key=**")
        await page.wait_for_load_state("networkidle")
        assert await page.get_by_text("Connection found", exact=True).count() == 1
        await page.screenshot(path=str(OUTPUT / "connection-desktop.png"), full_page=True)
        print("graph keyboard selection and path tracing OK", flush=True)
        await page.goto(DOCS + "/", wait_until="networkidle")
        assert page.url.startswith(DOCS)
        await page.get_by_role("button", name="Switch between light and dark theme").click()
        assert "dark" in (await page.locator("html").get_attribute("class") or "")
        await page.screenshot(path=str(OUTPUT / "docs-dark-desktop.png"))
        await page.get_by_role("button", name="Switch between light and dark theme").click()
        await page.locator(".lh-search").click()
        await page.get_by_role("combobox").fill("atomic")
        await page.get_by_role("option").first.wait_for()
        await page.screenshot(path=str(OUTPUT / "docs-search-desktop.png"))
        await page.get_by_role("option").first.click()
        await page.wait_for_load_state("networkidle")
        assert not await page.get_by_role("dialog").is_visible()
        await page.context.grant_permissions(["clipboard-read", "clipboard-write"])
        await page.get_by_role("button", name="Copy page", exact=True).click()
        await page.get_by_role("button", name="Copied", exact=True).wait_for()
        print("independent docs, theme, full-text search and copy OK", flush=True)
        await page.set_viewport_size({"width": 1440, "height": 1000})
        await page.goto(BASE + "/episodes?state=open", wait_until="networkidle")
        episode_path = await page.locator(
            "tbody tr td:nth-child(2) a"
        ).first.get_attribute("href")
        canonical = {
            "landing": "/",
            "dashboard": "/dashboard",
            "sources": "/sources",
            "agents": "/agents",
            "investigate": "/investigate",
            "ports-of-the-world": "/ports",
            "berths": "/berths",
            "desk": "/desk",
            "profile": "/profile",
            "ask-the-desk": "/desk/chat",
            "search": routes["search"],
            "port": selected_port,
            "episode": episode_path,
            "docs": DOCS + "/",
            "docs-reference": DOCS + "/reference",
        }
        for name, path in canonical.items():
            response = await page.goto(url(path), wait_until="networkidle")
            assert response.status == 200, (name, response.status)
            await prepare(page, name)
            if name in {"ports-of-the-world", "berths"}:
                # Table headers and values must share a table layout, not CSS grid.
                assert (
                    await page.locator("table.grid").evaluate(
                        "table => getComputedStyle(table).display"
                    )
                    == "table"
                )
                th = await page.locator("thead th").first.bounding_box()
                td = await page.locator("tbody td").first.bounding_box()
                assert abs(th["width"] - td["width"]) < 1, (
                    name,
                    "misaligned table columns",
                )
            await page.screenshot(
                path=str(args.output / f"{name}.png"),
                full_page=name
                not in {"ports-of-the-world", "berths", "desk", "docs-reference"},
            )
            print("updated screenshot", name, flush=True)
        await page.set_viewport_size({"width": 390, "height": 844})
        await page.goto(BASE + "/dashboard", wait_until="networkidle")
        await page.screenshot(
            path=str(args.output / "dashboard-phone.png"), full_page=True
        )
        assert not errors, errors
        (OUTPUT / "checks.json").write_text(
            json.dumps(
                {
                    "routes": routes,
                    "widths": [1440, 360, 390, 768, 1024],
                    "alignment": ["usable search width", "unbroken dates", "aligned agent footers", "readable chat suggestions", "card title and metadata separation", "table column widths", "activity icon and metadata alignment", "model selector width"],
                    "page_errors": errors,
                    "interactions": [
                        "Three.js harbor controls",
                        "interactive bento cards",
                        "reduced motion",
                        "WebGL fallback",
                        "inspector path endpoint selection",
                        "map regions",
                        "zoom/reset",
                        "signal filter",
                        "keyboard selection",
                        "port detail navigation",
                        "berth search/filter",
                        "berth detail navigation",
                        "port search/sort",
                        "country filter",
                        "mobile menu",
                        "refresh",
                        "graph keyboard selection",
                        "multi-hop path trace",
                        "docs search",
                        "docs themes",
                        "copy docs page",
                    ],
                },
                indent=2,
            )
        )
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())

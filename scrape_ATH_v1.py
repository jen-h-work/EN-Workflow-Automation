# Cell 1 — Imports
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import os
os.environ["WDM_SSL_VERIFY"] = "0"

import sys
sys.stdout.reconfigure(encoding="utf-8")

import re
import time
import pandas as pd

from selenium import webdriver
from selenium.webdriver.edge.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.microsoft import EdgeChromiumDriverManager


def log(message: str) -> None:
    print(message, flush=True)


# Cell 2 — Configuration
URL = "https://platform.atheneum-app.com/clientV2/p/c7ac4c6fe39c8b91d4917288f0026e7f4ffe1d32e460edd39df12b341271f60c/available"


# Cell 3 — Browser setup
def create_driver():
    log("Preparing Edge driver...")
    options = webdriver.EdgeOptions()
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--start-maximized")

    driver_path = EdgeChromiumDriverManager().install()
    log(f"Using Edge driver: {driver_path}")

    driver = webdriver.Edge(
        service=Service(driver_path),
        options=options
    )
    driver.set_page_load_timeout(45)
    driver.set_script_timeout(45)
    return driver


# Cell 4 — Atheneum scraper
def fetch_all_experts(url: str) -> list:
    driver = None
    experts = []

    try:
        driver = create_driver()
        log("Opening Atheneum page...")
        driver.get(url)

        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        log("Page loaded. Waiting for expert list...")
        time.sleep(5)

        # Optional diagnostic dump
        body_text = driver.find_element(By.TAG_NAME, "body").text
        with open("atheneum_page_dump.txt", "w", encoding="utf-8") as f:
            f.write(body_text)
        log("Saved diagnostic dump: atheneum_page_dump.txt")

        # Click load more / show more buttons
        load_more_labels = [
            "Load more",
            "Show more",
            "View more",
            "More experts",
            "See more"
        ]

        for load_more_count in range(50):
            clicked = False

            for label in load_more_labels:
                try:
                    btn = driver.find_element(
                        By.XPATH,
                        f"//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{label.lower()}')]"
                    )
                    driver.execute_script("arguments[0].scrollIntoView(true);", btn)
                    time.sleep(0.5)
                    driver.execute_script("arguments[0].click();", btn)
                    log(f"Clicked {label} ({load_more_count + 1})")
                    time.sleep(2)
                    clicked = True
                    break
                except:
                    continue

            if not clicked:
                break

        # Re-read full visible page
        lines = driver.find_element(By.TAG_NAME, "body").text.split("\n")
        lines = [l.strip() for l in lines if l.strip()]

        # Heuristic: Atheneum usually shows expert cards with name, role/company, location,
        # rate / availability / status nearby. This extracts candidate blocks.
        candidate_blocks = []
        current_block = []

        stop_markers = [
            "available experts",
            "shortlisted",
            "requested",
            "project",
            "filters",
            "sort",
            "log out"
        ]

        for line in lines:
            lower = line.lower()

            if any(marker in lower for marker in stop_markers):
                continue

            # New block likely starts at a person-like name line
            is_name_like = (
                len(line.split()) in [2, 3, 4]
                and len(line) < 80
                and not any(char.isdigit() for char in line)
                and not any(x in lower for x in ["eur", "gbp", "usd", "€", "£", "$", "available", "profile"])
            )

            if is_name_like:
                if current_block:
                    candidate_blocks.append(current_block)
                current_block = [line]
            elif current_block:
                current_block.append(line)

        if current_block:
            candidate_blocks.append(current_block)

        # Remove obvious non-expert blocks
        candidate_blocks = [
            block for block in candidate_blocks
            if len(block) >= 2 and len(block[0]) < 80
        ]

        log(f"Candidate expert blocks found: {len(candidate_blocks)}")

        seen_names = set()

        for i, block in enumerate(candidate_blocks):
            try:
                name = block[0]

                if name in seen_names:
                    continue
                seen_names.add(name)

                block_text = "\n".join(block)

                # Defaults
                role = ""
                company = ""
                geography = ""
                segment = ""
                rate = ""
                availability = ""
                screener = []

                # Role/company fallback
                if len(block) > 1:
                    role_company = block[1]

                    if " at " in role_company:
                        role, company = role_company.split(" at ", 1)
                    elif " - " in role_company:
                        parts = role_company.split(" - ")
                        role = parts[0].strip()
                        company = " - ".join(parts[1:]).strip()
                    else:
                        role = role_company

                # Geography: look for likely location lines
                geo_keywords = [
                    "United Kingdom", "UK", "London", "Germany", "France", "Spain",
                    "Italy", "Netherlands", "Europe", "United States", "USA",
                    "Switzerland", "Austria", "Belgium", "Nordics"
                ]
                geography = next(
                    (l for l in block if any(g.lower() in l.lower() for g in geo_keywords)),
                    ""
                )

                # Rate
                rate = next(
                    (l for l in block if re.search(r"(€|£|\$|EUR|GBP|USD)\s?\d+", l, re.I)),
                    ""
                )

                # Availability / status
                availability = next(
                    (l for l in block if any(x in l.lower() for x in [
                        "available", "availability", "can speak", "responded",
                        "interested", "pending", "scheduled"
                    ])),
                    ""
                )

                # Segment / expertise fallback
                segment = next(
                    (l for l in block[2:] if l not in [geography, rate, availability] and len(l) < 120),
                    ""
                )

                # Screener responses: extract numbered Q&A if present
                for idx, line in enumerate(block):
                    if re.match(r"^\d+[\.\)]", line):
                        answer = block[idx + 1] if idx + 1 < len(block) else "No answer"
                        screener.append({
                            "question": line,
                            "answer": answer
                        })

                experts.append({
                    "name": name,
                    "company": company,
                    "role": role,
                    "geography": geography,
                    "segment": segment,
                    "rate": rate,
                    "availability": availability,
                    "screener_responses": screener,
                    "raw_block": block_text
                })

                log(f"Extracted ({len(experts)}): {name}")

            except Exception as e:
                log(f"Error on candidate block {i + 1}: {e}")
                continue

    except Exception as e:
        log(f"Fatal error: {e}")

    finally:
        if driver is not None:
            driver.quit()

    return experts


# Cell 5 — Display as table
def display_as_table(experts: list):
    rows = []

    for e in experts:
        screener_text = "\n".join(
            [f"Q: {qa['question']}\nA: {qa['answer']}" for qa in e["screener_responses"]]
        ) if e["screener_responses"] else "None"

        rows.append({
            "Name": e["name"],
            "Geography": e["geography"],
            "Segment": e["segment"],
            "Rate": e["rate"],
            "Role": e["role"],
            "Company": e["company"],
            "Screener Responses": screener_text,
            "Availability": e["availability"],
            "Raw Block": e["raw_block"]
        })

    df = pd.DataFrame(rows)
    pd.set_option("display.max_colwidth", None)
    pd.set_option("display.max_rows", None)
    return df


# Cell 6 — Run
def main():
    log("Starting scrape_ATH.py...")

    experts = fetch_all_experts(URL)
    df = display_as_table(experts)

    log(f"Rows scraped: {len(df)}")

    if df.empty:
        log("No rows were scraped. Check atheneum_page_dump.txt to inspect page text.")
    else:
        df.to_excel("atheneum_experts.xlsx", index=False)
        df.to_csv("atheneum_experts.csv", index=False, encoding="utf-8-sig")
        log("Saved outputs: atheneum_experts.xlsx and atheneum_experts.csv")

    return df


if __name__ == "__main__":
    df = main()
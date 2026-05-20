# Cell 1 — Imports
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
# Suppresses the SSL warning that appears when verify=False is used

import os
os.environ['WDM_SSL_VERIFY'] = '0' #another SSL fix

import sys
sys.stdout.reconfigure(encoding="utf-8") #force UTF8 output

import re
# Regex library- to detect numbered screener questions e.g. "1."

from selenium import webdriver
from selenium.webdriver.edge.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.microsoft import EdgeChromiumDriverManager
import time
import pandas as pd


def log(message: str) -> None:
    print(message, flush=True)


# Cell 2 — Configuration
URL = "https://platform.prosapient.com/client/projects/ef3ae048-29ac-46c6-9b36-66a2a3a9fd60/experts/c2ce1c89-6914-44ea-97fd-0f86fc484d4b?ga=0q13m5I4yLRCxbIbSdEz-Ohz2bQKsG7i7ixmKnxgVGtcjVFLLCHBZaUNkUHhA3Lm&utm_campaign=Expert_list_external_link&utm_medium=link&utm_source=bio_email"

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
        # Updated to match the new class name
        options=options
    )
    driver.set_page_load_timeout(45)
    driver.set_script_timeout(45)
    return driver

# Cell 4 v2 — Fixed: extract geo/segment before click, screener after click
def fetch_all_experts(url: str) -> list:
    driver = None
    experts = []

    try:
        driver = create_driver()
        log("Opening proSapient page...")
        driver.get(url)
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        log("Page loaded. Waiting for expert list...")
        time.sleep(3)

        # Click "Load more" until all experts are visible
        for load_more_count in range(50):
            try:
                load_more = driver.find_element(By.XPATH, "//button[contains(text(), 'Load more')]")
                driver.execute_script("arguments[0].click();", load_more)
                log(f"Clicked Load more ({load_more_count + 1})")
                time.sleep(2)
            except:
                break
        else:
            log("Stopped after 50 Load more clicks; continuing with visible experts.")

        # Step 1 — Extract all data from collapsed list BEFORE any clicking
        # At this point geo, segment, rate, availability are all visible in list view
        pre_click_lines = driver.find_element(By.TAG_NAME, "body").text.split('\n')
        pre_click_lines = [l.strip() for l in pre_click_lines if l.strip()]

        # Build a lookup of name -> {geo, segment, rate, availability}
        # Structure in list view: role_company / • Name / geo / segment / rate / status
        pre_click_data = {}
        for idx, line in enumerate(pre_click_lines):
            if line.startswith('•'):
                name = line.replace('•', '').strip()
                name = ''.join(c for c in name if c.isalnum() or c in ' .,()-')
                geo          = pre_click_lines[idx + 1] if idx + 1 < len(pre_click_lines) else ""
                segment      = pre_click_lines[idx + 2] if idx + 2 < len(pre_click_lines) else ""
                rate         = pre_click_lines[idx + 3] if idx + 3 < len(pre_click_lines) else ""
                availability = pre_click_lines[idx + 4] if idx + 4 < len(pre_click_lines) else ""
                pre_click_data[name] = {
                    "geography":    geo,
                    "segment":      segment,
                    "rate":         rate,
                    "availability": availability
                }

        log(f"Total experts found: {len(pre_click_data)}")

        # Step 2 — Click each expert to get role, company, and screener responses
        for i, name in enumerate(pre_click_data.keys()):
            try:
                first_word = name.split()[0]

                # Find bullet element fresh each time by expert's first name
                expert_el = driver.find_element(
                    By.XPATH,
                    f"//*[contains(text(), '•') and contains(text(), '{first_word}')]"
                )

                # Save name text before click to avoid stale reference
                driver.execute_script(
                    "arguments[0].scrollIntoView(true); window.scrollBy(0, -150);",
                    expert_el
                )
                time.sleep(1)
                driver.execute_script("arguments[0].click();", expert_el)
                time.sleep(2)

                # Get fresh page content after profile expands
                post_lines = driver.find_element(By.TAG_NAME, "body").text.split('\n')
                post_lines = [l.strip() for l in post_lines if l.strip()]

                # Find name in expanded content (no bullet, short line, after navbar)
                name_idx = next(
                    (idx for idx, l in enumerate(post_lines)
                     if first_word in l and '•' not in l
                     and len(l) < 80 and idx > 10),
                    None
                )

                if name_idx is None:
                    log(f"  Skipping {name} — could not locate expanded content")
                    continue

                # Role and company: line immediately before name (line 64 in diagnostic)
                role_company = post_lines[name_idx - 1] if name_idx > 0 else ""
                if ' - ' in role_company:
                    company = role_company.split(' - ')[0].strip()
                    role    = ' - '.join(role_company.split(' - ')[1:]).strip()
                else:
                    company = role_company
                    role    = ""

                # Screener: starts at line after work experience (line 67 in diagnostic)
                # Skip line 66 (full work experience) and start from name_idx + 2
                screener = []
                stop_words = ["Show work experience", "Contact proSapient",
                              "Contact expert", "Schedule a call",
                              "Add to shortlist", "Not interested"]
                j = name_idx + 2
                # Starts at +2 to skip the long work experience line (line 66)
                while j < len(post_lines):
                    if re.match(r'^\d+\.', post_lines[j]):
                        question = post_lines[j]
                        answer = post_lines[j + 1] if (
                            j + 1 < len(post_lines) and
                            not re.match(r'^\d+\.', post_lines[j + 1]) and
                            post_lines[j + 1] not in stop_words
                        ) else "No answer"
                        screener.append({"question": question, "answer": answer})
                        j += 2
                    elif post_lines[j] in stop_words:
                        break
                    else:
                        j += 1

                # Merge pre-click data with post-click data
                entry = pre_click_data[name]
                experts.append({
                    "name":               name,
                    "company":            company,
                    "role":               role,
                    "geography":          entry["geography"],
                    "segment":            entry["segment"],
                    "rate":               entry["rate"],
                    "availability":       entry["availability"],
                    "screener_responses": screener
                })

                log(f"Extracted ({i+1}/{len(pre_click_data)}): {name}")

            except Exception as e:
                log(f"Error on expert {i+1} ({name}): {e}")
                continue

    except Exception as e:
        log(f"Fatal error: {e}")
    finally:
        if driver is not None:
            driver.quit()

    return experts

# Cell 5 — Display as table #use cell 7 instead if not working
def display_as_table(experts: list):
    rows = []
    for e in experts:
        screener_text = "\n".join(
            [f"Q: {qa['question']}\nA: {qa['answer']}" for qa in e['screener_responses']]
        ) if e['screener_responses'] else "None"

        rows.append({
            "Name":               e['name'],
            "Geography":          e['geography'],
            "Segment":            e['segment'],
            "Rate":               e['rate'],
            "Role":               e['role'],
            "Company":            e['company'],
            "Screener Responses": screener_text,
            "Availability":       e['availability']
        })

    df = pd.DataFrame(rows)
    pd.set_option('display.max_colwidth', None)
    pd.set_option('display.max_rows', None)
    return df

# Cell 6 — Run
def main():
    log("Starting scrape_PS.py...")
    experts = fetch_all_experts(URL)
    df = display_as_table(experts)
    log(f"Rows scraped: {len(df)}")

    if df.empty:
        log("No rows were scraped.")
    else:
        df.to_excel("prosapient_experts.xlsx", index=False)
        df.to_csv("prosapient_experts.csv", index=False, encoding="utf-8-sig")
        log("Saved outputs: prosapient_experts.xlsx and prosapient_experts.csv")

    return df

if __name__ == "__main__":
    main()


# Cell 7 — Display results as a table #to be used instead of cells 5 and 6 if they fail
"""
import pandas as pd
# Pandas library for creating and displaying structured tables

def display_as_table(experts: list):
    rows = []
    for e in experts:
        # Format screener Q&A into readable multiline text for the table cell
        if e['screener_responses']:
            screener_text = "\n".join(
                [f"Q: {qa['question']}\nA: {qa['answer']}" for qa in e['screener_responses']]
            )
        else:
            screener_text = "None"

        rows.append({
            "Name":               e['name'],
            "Geography":          e['geography'],
            "Segment":            e['segment'],
            "Role":               e['role'],
            "Company":            e['company'],
            "Screener Responses": screener_text,
            "Availability":       e['availability']
        })

    df = pd.DataFrame(rows)
    # Creates a structured table from the list of dictionaries

    # Display settings — shows full text without truncation
    pd.set_option('display.max_colwidth', None)
    pd.set_option('display.max_rows', None)

    return df

df = display_as_table(experts)
df
# In Jupyter, ending a cell with a variable name displays it as a formatted table
"""



# Cell 8 — Diagnostic: grab name first, then click, then inspect lines
"""
def diagnose_parsing(url: str) -> None:
    driver = create_driver()
    try:
        driver.get(url)
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        time.sleep(3)

        # Step 1 — Get name text BEFORE clicking (avoids stale reference)
        expert_el = driver.find_element(By.XPATH, "//*[contains(text(), '•')]")
        name_raw = expert_el.text.replace('•', '').strip()
        first_word = name_raw.split()[0]
        print(f"Clicking expert: {name_raw}")

        # Step 2 — Scroll and click
        driver.execute_script(
            "arguments[0].scrollIntoView(true); window.scrollBy(0, -150);",
            expert_el
        )
        time.sleep(1)
        driver.execute_script("arguments[0].click();", expert_el)
        time.sleep(2)

        # Step 3 — Now get fresh page content AFTER click
        # expert_el is intentionally not used again after this point
        lines = driver.find_element(By.TAG_NAME, "body").text.split('\n')
        lines = [l.strip() for l in lines if l.strip()]

        # Step 4 — Find name in expanded content
        name_idx = next(
            (idx for idx, l in enumerate(lines)
             if first_word in l and '•' not in l and len(l) < 80 and idx > 10),
            None
        )

        if name_idx:
            print(f"\nName '{name_raw}' found at line {name_idx}")
            print("\n--- Raw lines around expert (lines -2 to +15) ---")
            for idx in range(max(0, name_idx - 2), min(len(lines), name_idx + 15)):
                print(f"  Line {idx:3}: {lines[idx]}")
        else:
            print(f"Could not find '{name_raw}' in page content")
            print("\n--- First 50 lines of page for inspection ---")
            for idx, l in enumerate(lines[:50]):
                print(f"  Line {idx:3}: {l}")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        driver.quit()

diagnose_parsing(URL)
"""

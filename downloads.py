# ============================================================
# DOWNLOAD ANNUAL REPORT PDFs FROM URLS IN CSV
# ============================================================

import os
import re
import time
import requests
import pandas as pd
from pathlib import Path
from urllib.parse import urlparse

# ============================================================
# CONFIGURATION
# ============================================================

INPUT_CSV = "sources_new_updated.csv"

# Column containing the NSE PDF URL
URL_COLUMN = "Alternative pdf url"

# Column containing company names
COMPANY_COLUMN = "Company Name"

# Folder where PDFs will be saved
PDF_FOLDER = Path("downloaded_reports")

# Request settings
REQUEST_TIMEOUT = 60
MAX_RETRIES = 3
RETRY_DELAY = 3

# ============================================================
# CREATE PDF FOLDER
# ============================================================

PDF_FOLDER.mkdir(parents=True, exist_ok=True)


# ============================================================
# SAFE COMPANY NAME
# ============================================================

def safe_filename(company_name):

    name = str(company_name).strip()

    # Remove characters not allowed in Windows filenames
    name = re.sub(r'[<>:"/\\|?*]', '', name)

    # Remove extra spaces
    name = re.sub(r'\s+', ' ', name)

    return name.strip()


# ============================================================
# CHECK IF ALREADY DOWNLOADED
# ============================================================

def already_downloaded(company_name):

    filename = safe_filename(company_name) + ".pdf"

    path = PDF_FOLDER / filename

    return path.exists() and path.stat().st_size > 10_000


# ============================================================
# DOWNLOAD ONE PDF
# ============================================================

def download_pdf(company_name, pdf_url):

    filename = safe_filename(company_name) + ".pdf"

    output_path = PDF_FOLDER / filename

    # --------------------------------------------------------
    # Skip if already downloaded
    # --------------------------------------------------------

    if already_downloaded(company_name):

        print(f"   SKIP - already downloaded")
        print(f"   {output_path}")

        return True


    # --------------------------------------------------------
    # Validate URL
    # --------------------------------------------------------

    if not pdf_url:

        print("   No PDF URL")

        return False


    pdf_url = str(pdf_url).strip()

    if pdf_url.lower() in [
        "",
        "nan",
        "none",
        "null",
        "not for this year"
    ]:

        print("   No valid PDF URL")

        return False


    print(f"   URL:")
    print(f"   {pdf_url}")


    # --------------------------------------------------------
    # Headers
    # --------------------------------------------------------

    headers = {

        "User-Agent":
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36",

        "Accept":
            "application/pdf,text/html;q=0.9,*/*;q=0.8",

        "Referer":
            "https://www.nseindia.com/"
    }


    # --------------------------------------------------------
    # Retry
    # --------------------------------------------------------

    for attempt in range(1, MAX_RETRIES + 1):

        try:

            print(
                f"   Download attempt "
                f"{attempt}/{MAX_RETRIES}"
            )

            response = requests.get(
                pdf_url,
                headers=headers,
                timeout=REQUEST_TIMEOUT
            )


            print(
                f"   HTTP status: "
                f"{response.status_code}"
            )


            # ------------------------------------------------
            # Check HTTP status
            # ------------------------------------------------

            response.raise_for_status()


            # ------------------------------------------------
            # Get content
            # ------------------------------------------------

            content = response.content


            # ------------------------------------------------
            # Validate PDF
            # ------------------------------------------------

            if len(content) < 10_000:

                print(
                    "   Downloaded file is too small."
                )

                raise ValueError(
                    "Downloaded content is not a valid PDF"
                )


            # PDF files normally start with %PDF
            if not content[:10].startswith(b"%PDF"):

                print(
                    "   WARNING: response does not "
                    "start with %PDF"
                )

                content_type = response.headers.get(
                    "Content-Type",
                    ""
                ).lower()

                print(
                    f"   Content-Type: {content_type}"
                )

                # Don't save HTML/error pages as PDFs
                if "pdf" not in content_type:

                    raise ValueError(
                        "Response does not appear to be a PDF"
                    )


            # ------------------------------------------------
            # Save PDF
            # ------------------------------------------------

            output_path.write_bytes(content)


            print(
                f"   SUCCESS"
            )

            print(
                f"   Saved: {output_path}"
            )

            print(
                f"   Size: "
                f"{len(content) / (1024 * 1024):.2f} MB"
            )

            return True


        except Exception as e:

            print(
                f"   ERROR: {e}"
            )

            if attempt < MAX_RETRIES:

                print(
                    f"   Retrying in "
                    f"{RETRY_DELAY} seconds..."
                )

                time.sleep(RETRY_DELAY)


    print(
        "   FAILED after all retries."
    )

    return False


# ============================================================
# MAIN
# ============================================================

def main():

    print("\n")
    print("=" * 70)
    print("NSE ANNUAL REPORT PDF DOWNLOADER")
    print("=" * 70)


    # --------------------------------------------------------
    # Load CSV
    # --------------------------------------------------------

    if not os.path.exists(INPUT_CSV):

        raise FileNotFoundError(
            f"CSV not found: {INPUT_CSV}"
        )


    df = pd.read_csv(INPUT_CSV)


    # --------------------------------------------------------
    # Validate columns
    # --------------------------------------------------------

    if COMPANY_COLUMN not in df.columns:

        raise ValueError(
            f"Missing column: {COMPANY_COLUMN}"
        )


    if URL_COLUMN not in df.columns:

        raise ValueError(
            f"Missing column: {URL_COLUMN}"
        )


    print(
        f"\nTotal companies: {len(df)}"
    )

    print(
        f"PDF folder: {PDF_FOLDER.absolute()}"
    )


    # --------------------------------------------------------
    # Counters
    # --------------------------------------------------------

    downloaded = 0
    skipped = 0
    failed = 0
    no_url = 0


    # --------------------------------------------------------
    # Process companies
    # --------------------------------------------------------

    for index, row in df.iterrows():

        company_name = str(
            row[COMPANY_COLUMN]
        ).strip()


        pdf_url = row[URL_COLUMN]


        print("\n")
        print("=" * 70)

        print(
            f"[{index + 1}/{len(df)}] "
            f"{company_name}"
        )

        print("=" * 70)


        # ----------------------------------------------------
        # Empty company
        # ----------------------------------------------------

        if not company_name or company_name.lower() == "nan":

            print("   Invalid company name")

            failed += 1

            continue


        # ----------------------------------------------------
        # Check URL
        # ----------------------------------------------------

        if pd.isna(pdf_url):

            print("   No URL in CSV")

            no_url += 1

            continue


        pdf_url = str(pdf_url).strip()


        if pdf_url.lower() in [
            "",
            "nan",
            "none",
            "null",
            "not for this year"
        ]:

            print("   No PDF URL")

            no_url += 1

            continue


        # ----------------------------------------------------
        # Existing PDF
        # ----------------------------------------------------

        if already_downloaded(company_name):

            print(
                "   SKIPPED - PDF already exists"
            )

            skipped += 1

            continue


        # ----------------------------------------------------
        # Download
        # ----------------------------------------------------

        success = download_pdf(
            company_name,
            pdf_url
        )


        if success:

            downloaded += 1

        else:

            failed += 1


        # Small delay between companies
        time.sleep(1)


    # ========================================================
    # FINAL SUMMARY
    # ========================================================

    print("\n")
    print("=" * 70)
    print("DOWNLOAD COMPLETE")
    print("=" * 70)

    print(
        f"Total companies : {len(df)}"
    )

    print(
        f"Downloaded      : {downloaded}"
    )

    print(
        f"Already existed : {skipped}"
    )

    print(
        f"No URL          : {no_url}"
    )

    print(
        f"Failed          : {failed}"
    )

    print(
        f"\nPDF folder:"
    )

    print(
        PDF_FOLDER.absolute()
    )

    print("=" * 70)


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()
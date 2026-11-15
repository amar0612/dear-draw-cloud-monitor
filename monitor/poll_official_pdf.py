
import argparse
import time
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

BASE_URL = "https://www.nagalandlotteries.com/old_results/"

def check_result(draw, date_code):
    prefix = "MN" if draw == "1pm" else "EN"
    filename = f"{prefix}{date_code}.PDF"
    url = BASE_URL + filename

    try:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "DearDrawAnalyzer/1.0"}
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            data = response.read(1024)

        if data.startswith(b"%PDF-"):
            print(f"PDF AVAILABLE: {url}")
            return True

        print("Response is not a valid PDF.")
        return False

    except Exception as error:
        print(f"Not available yet: {error}")
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--draw", choices=["1pm", "8pm"], required=True)
    parser.add_argument("--date", help="Date in DDMMYY format")
    args = parser.parse_args()

    date_code = args.date or datetime.now(
        ZoneInfo("Asia/Kolkata")
    ).strftime("%d%m%y")

    for attempt in range(1, 12):
        print(f"Check {attempt}/11: {args.draw} draw")

        if check_result(args.draw, date_code):
            print("PDF detected. Manual verification is still required.")
            return

        if attempt < 11:
            time.sleep(60)

    print("No PDF found after 11 checks. Manual review required.")


if __name__ == "__main__":
    main()

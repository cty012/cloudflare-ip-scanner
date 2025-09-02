#!/usr/bin/env python3
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import ipaddress
import math
import platform
import requests
import socket
import subprocess
import sys
import threading
import time
from typing import Optional


# --- ANSI Escape Codes for Formatting ---
class Ansi:
    """A helper class for ANSI escape codes for terminal colors and styles."""
    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
    # ANSI codes for cursor manipulation
    CURSOR_UP = "\033[A"
    CLEAR_LINE = "\033[K"
    CLEAR_SCREEN_FROM_CURSOR = "\033[J"


def get_cloudflare_ips() -> Optional[list[str]]:
    """
    Fetches the list of Cloudflare IPv4 CIDR ranges from their official API.
    Returns a list of CIDR strings.
    """
    try:
        response = requests.get("https://api.cloudflare.com/client/v4/ips", timeout=10)
        response.raise_for_status()
        data = response.json()
        if data.get("success") and "ipv4_cidrs" in data["result"]:
            return data["result"]["ipv4_cidrs"]
        else:
            print(f"{Ansi.RED}Error: Could not fetch Cloudflare IP list. Response was not successful.{Ansi.ENDC}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"{Ansi.RED}Error fetching Cloudflare IPs: {e}{Ansi.ENDC}")
        return None


def expand_cidrs(cidrs: list[str]) -> list[str]:
    """
    Expands a list of CIDR ranges into a list of individual IP addresses.
    For small blocks (>= 24 fixed bits), it tests all IPs.
    For larger blocks, it tests only IPs with the last 4 bits 0.
    """
    ips = []
    for cidr in cidrs:
        try:
            net = ipaddress.ip_network(cidr)
            # Cloudflare network addresses also respond to pings, so we include them
            if net.prefixlen >= 24:
                ips.extend([str(ip) for ip in net])
            else:
                for ip_obj in net:
                    if int(ip_obj) % 16 == 0:
                        ips.append(str(ip_obj))
        except ValueError as e:
            print(f"{Ansi.YELLOW}Warning: Could not parse CIDR {cidr}: {e}{Ansi.ENDC}")
    return list(set(ips))


def get_ip_location(ip: str) -> str:
    """
    Fetches the physical location of an IP address using ipinfo.io,
    which is more reliable in China.
    """
    try:
        response = requests.get(f"https://ipinfo.io/{ip}/json", timeout=10)
        response.raise_for_status()
        data = response.json()
        city = data.get("city", "N/A")
        country = data.get("country", "N/A")
        return f"{city}, {country}"
    except requests.exceptions.RequestException:
        return "Network Error"


def ping_ip(ip: str, n_tries: int=4, timeout: float=1.0) -> Optional[float]:
    """
    Pings a single IP address multiple times and returns the average latency.
    Returns None if the ping fails or times out.

    The ping command uses the TCP protocol to connect to the 443 port of the target IP.

    Note: n_tries must be at least 1. 3 is the recommended minimum.
    """
    latencies = []

    for _ in range(n_tries):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)

        start_time = time.perf_counter()
        try:
            if s.connect_ex((ip, 443)) == 0:
                end_time = time.perf_counter()
                s.shutdown(socket.SHUT_RDWR)
                latencies.append((end_time - start_time) * 1000)
            else:
                return None
        except socket.error:
            return None
        finally:
            s.close()

    return sum(latencies) / len(latencies)


def to_time_str(seconds: int) -> str:
    """Converts seconds to a human-readable time string."""
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}h {minutes:02}m {seconds:02}s"
    elif minutes > 0:
        return f"{minutes}m {seconds:02}s"
    else:
        return f"{seconds}s"


# Use a static variable inside the function to track its state
def display_results_table(
        results: list[dict], tested_count: int, total_count: int,
        te: float, etr: float,
        new_results_available: bool, custom_msg: str=None) -> None:

    """Clears the previously printed lines and displays the current results table."""
    if not hasattr(display_results_table, "num_lines_table"):
        display_results_table.num_lines_table = 0
    if not hasattr(display_results_table, "num_lines_progress_bar"):
        display_results_table.num_lines_progress_bar = 0

    prev_nl_table = display_results_table.num_lines_table
    prev_nl_progress_bar = display_results_table.num_lines_progress_bar

    lines_to_print_table = []
    lines_to_print_progress_bar = []

    # --- Table ---
    if new_results_available:
        header = f"{Ansi.BOLD}{Ansi.HEADER}{'Rank':<8}{'IP Address':<18}{'Location':<30}{'Latency (ms)':<10}{Ansi.ENDC}"
        separator = "-" * 70
        lines_to_print_table.append(header)
        lines_to_print_table.append(separator)

        for i, res in enumerate(results):
            rank = i + 1
            ip = res["ip"]
            location = res.get("location", "...")
            latency = f"{res['latency']:.2f}"
            latency_val = res["latency"]
            color = Ansi.GREEN if latency_val < 100 else Ansi.YELLOW if latency_val < 200 else Ansi.RED
            lines_to_print_table.append(f"{rank:<8}{ip:<18}{location:<30}{color}{latency:<10}{Ansi.ENDC}")

        display_results_table.num_lines_table = len(lines_to_print_table)

    # --- Progress Bar ---
    lines_to_print_progress_bar.append("")  # Spacer line
    if custom_msg is None:
        progress_bar_length = 40
        progress = int((tested_count / total_count) * progress_bar_length) if total_count > 0 else 0
        progress_bar_str = f"[{'█' * progress}{'-' * (progress_bar_length - progress)}]"
        te_str = to_time_str(math.ceil(te))
        etr_str = to_time_str(math.ceil(etr))
        progress_line = (f"{Ansi.YELLOW}Scanning Progress: {Ansi.ENDC}"
                         f"{progress_bar_str}"
                         f"{Ansi.YELLOW} {tested_count}/{total_count}{Ansi.ENDC}")
        time_line = f"{Ansi.YELLOW}Time elapsed: {te_str}  Estimated time remaining: {etr_str}{Ansi.ENDC}"
        lines_to_print_progress_bar.append(progress_line)
        lines_to_print_progress_bar.append(time_line)
    else:
        lines_to_print_progress_bar.append(custom_msg)
    display_results_table.num_lines_progress_bar = len(lines_to_print_progress_bar)

    # --- Clear previous output and move the cursor up ---
    # Clear the table only if new results are available
    num_lines_to_clear = (prev_nl_table + prev_nl_progress_bar) if new_results_available else prev_nl_progress_bar
    output_buffer = (Ansi.CURSOR_UP + Ansi.CLEAR_LINE) * num_lines_to_clear

    # --- Print all lines ---
    if len(lines_to_print_table) > 0:
        output_buffer += "\n".join(lines_to_print_table) + "\n"
    if len(lines_to_print_progress_bar) > 0:
        output_buffer += "\n".join(lines_to_print_progress_bar) + "\n"
    print(output_buffer, end="", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Test Cloudflare IPs for TCP connection latency.",
                                     formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--ip-list", type=str, help="if specified, load Cloudflare IPs from the local file (comma or newline-delimited list)")
    parser.add_argument("--limit", type=int, default=20, help="display a limited number of IPs with the lowest latency (default: 20)")
    parser.add_argument("--max-latency", type=int, help="only show IPs with a latency below the specified milliseconds")
    parser.add_argument("--out", type=str, help="save the results to the file")
    args = parser.parse_args()

    # --- Step 1: Fetch all Cloudflare IPs to test ---
    cidrs = None
    if args.ip_list is None:
        print(f"{Ansi.CYAN}Fetching Cloudflare IP ranges...{Ansi.ENDC}")
        cidrs = get_cloudflare_ips()
    else:
        print(f"{Ansi.CYAN}Loading Cloudflare IP ranges from {args.ip_list}...{Ansi.ENDC}")
        with open(args.ip_list, "r") as f:
            content = f.read().replace(",", "\n").splitlines()
            # Split by comma or newline and strip whitespace
            cidrs = [cidr.strip() for cidr in content if cidr.strip()]
    if cidrs is None:
        sys.exit(1)

    print(f"{Ansi.CYAN}Expanding CIDR ranges...{Ansi.ENDC}")
    ips_to_test = expand_cidrs(cidrs)
    total_ips = len(ips_to_test)
    print(f"{Ansi.GREEN}Found {total_ips} unique IP addresses to test.{Ansi.ENDC}\n")

    # --- Step 2: Fetch all cloudflare IPs ---
    results = []
    tested_count = 0
    new_results_available = False
    lock = threading.Lock()

    # Create a small, separate thread pool for location lookups to avoid blocking
    location_executor = ThreadPoolExecutor(max_workers=5)

    def process_location(ip_obj):
        """Callback to update location asynchronously."""
        nonlocal new_results_available
        location = get_ip_location(ip_obj["ip"])
        with lock:
            ip_obj["location"] = location
            new_results_available = True

    # Time estimation
    start_time = time.time()
    prev_time = start_time
    rate = 0  # seconds/item
    alpha = 0.95

    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_ip = {executor.submit(ping_ip, ip): ip for ip in ips_to_test}

        for future in as_completed(future_to_ip):
            ip = future_to_ip[future]
            tested_count += 1

            try:
                latency = future.result()
                if latency is None:
                    continue

                if args.max_latency is not None and latency >= args.max_latency:
                    continue

                with lock:
                    # Check if this new IP can make it into the top list
                    is_top = len(results) < args.limit or latency < results[args.limit - 1]["latency"]

                    if is_top:
                        # Fetch its location
                        ip_obj = {"ip": ip, "latency": latency}
                        location_executor.submit(process_location, ip_obj)

                        # Add the result to the list
                        results.append(ip_obj)
                        results.sort(key=lambda x: x["latency"])
                        results = results[:args.limit]
                        new_results_available = True

            except Exception:
                pass

            finally:
                # Update estimated time
                new_time = time.time()
                if tested_count == 1:
                    rate = new_time - prev_time
                else:
                    rate = alpha * rate + (1 - alpha) * (new_time - prev_time)
                prev_time = new_time

                # Calculate time elapsed (te) and estimated time remaining (etr)
                te = new_time - start_time
                etr = (total_ips - tested_count) * rate

                # Update display every loop
                with lock:
                    is_finished = tested_count == total_ips
                    custom_msg = None
                    if is_finished:
                        custom_msg = f"{Ansi.YELLOW}Waiting for location lookups to finish...{Ansi.ENDC}"

                    display_results_table(results, tested_count, total_ips, te, etr, new_results_available, custom_msg)
                    new_results_available = False

    # Wait for any outstanding location lookups to finish
    location_executor.shutdown(wait=True)

    # --- Step 3: Final display and save to file ---
    with lock:
        custom_msg = f"{Ansi.GREEN}Scanning complete.{Ansi.ENDC}"
        display_results_table(results, tested_count, total_ips, te, etr, new_results_available, custom_msg)

    if args.out:
        with open(args.out, "w") as f:
            f.write(f"{'Rank':<8}{'IP Address':<18}{'Location':<30}{'Latency (ms)':<10}\n")
            f.write("-" * 70 + "\n")
            for i, res in enumerate(results):
                f.write(f"{i + 1:<8}{res['ip']:<18}{res.get('location', 'N/A'):<30}{res['latency']:.2f}\n")
        print(f"{Ansi.GREEN}Results saved to {args.out}{Ansi.ENDC}")


def test():
    print(ping_ip("www.baidu.com"))
    print(ping_ip("www.google.com"))


if __name__ == "__main__":
    main()
    # test()

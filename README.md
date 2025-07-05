# Cloudflare IP Scanner

This script tests Cloudflare's IP ranges to find the one with the lowest latency from your current network location. It's a useful tool for optimizing network settings to connect to Cloudflare's network more efficiently.

The script fetches Cloudflare's official IP ranges, pings a sample of these IPs to measure round-trip time, and displays a real-time, sorted list of the fastest IPs.

## Features

*   **Fetches Official IPs**: Automatically gets the latest IPv4 CIDR blocks from the Cloudflare API. Can also load from a local file with IP ranges.
*   **Efficient IP Sampling**: Tests all IPs in smaller subnets (`/24` or larger prefix) and uses a smart sampling method for larger subnets to reduce scan time.
*   **Concurrent Scanning**: Uses multithreading to test multiple IPs simultaneously for faster results.
*   **Real-time Results**: Displays a continuously updated and sorted table of the fastest IPs found so far.
*   **Geolocation**: Fetches the city and country for the top-performing IPs.
*   **Customizable**: Use command-line arguments to limit the number of results, set a maximum latency, and save results to a file.
*   **Cross-Platform**: Works on macOS, Linux, and Windows.

## Requirements

*   Python 3.x
*   `requests` library

## Installation

1.  Clone the repository or download the `cloudflare-ip-scanner.py` script.
2.  Install the required Python package:
    ```bash
    pip install requests
    ```

## Usage

Run the script from your terminal.

**Basic Usage**

This will scan the IPs and display the top 20 fastest results.

```bash
python3 cloudflare-ip-scanner.py
```

### Command-Line Arguments (Optional)

*   `--limit <N>`: Display the top `N` IPs with the lowest latency. (Default: 20)
*   `--max-latency <ms>`: Only show IPs with a latency below the specified milliseconds.
*   `--out <filename>`: Save the final results to a specified file.
*   `--ip-list <filename>`: Load IP ranges from a local file instead of fetching from the Cloudflare API. The file can be a comma-separated or newline-delimited list of CIDRs.

### Examples

**Show the top 10 results:**

```bash
./cloudflare-ip-scanner.py --limit 10
```

**Only show IPs with latency under 150ms and save to `results.txt`:**

```bash
./cloudflare-ip-scanner.py --max-latency 150 --out results.txt
```

**Use a local file for IP ranges:**

```bash
./cloudflare-ip-scanner.py --ip-list ip_list.txt
```
#!/bin/bash

# A script to execute a command and print the elapsed time in milliseconds.

# Check if a command was provided as an argument.
# If not, print a usage message to stderr and exit with an error code.
if [ "$#" -eq 0 ]; then
    echo "Usage: $0 <command>" >&2
    exit 1
fi

# Get the start time in nanoseconds. %s is seconds, %N is nanoseconds.
start_time=$(date +%s%N)

# Execute the command passed to the script ("$@").
# Redirect its standard output (stdout) and standard error (stderr) to /dev/null.
# This ensures that this timer script *only* outputs the final time value.
"$@" > /dev/null 2>&1
# Capture the exit code of the subcommand immediately after it runs.
subcommand_exit_code=$?

# Get the end time in nanoseconds.
end_time=$(date +%s%N)

# Calculate the duration. The result is in nanoseconds.
# We then divide by 1,000,000 to convert to milliseconds.
# The $((...)) syntax is for arithmetic expansion in bash.
duration_ms=$(( (end_time - start_time) / 1000000 ))

# Print the final duration in milliseconds.
echo $duration_ms

# Exit with the captured exit code of the subcommand.
exit $subcommand_exit_code

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run a command, add output it to the action output"""
import os
import sys
import argparse
import subprocess

DEBUG_INFO = False


# -----------------------------------------------------------------------------
def run(cmd, args_list):
    """Run a shell command and return the error code.

    :param cmd_list: A list of strings that make up the command to execute.
    """
    # Need to special-case a single arg, as the GitHub Action docker
    # environment sends all arguments in a single string
    if len(args_list) == 1:
        cmds = "{} {}".format(cmd, args_list[0])
        shell = True
    else:
        cmds = [cmd, *args_list]
        shell = False

    print("Running: {}\n".format(cmds), flush=True)
    try:
        process_output = subprocess.run(
            cmds,
            shell=shell,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
    except Exception as e:
        print("Error running the command:", flush=True)
        print(str(e))
        sys.exit(1)

    if process_output.returncode != 0:
        print("CompletedProcess data:")
        print(process_output)
        print("\nProcess exited with error code {}".format(process_output.returncode))
        sys.exit(process_output.returncode)

    return process_output


# -----------------------------------------------------------------------------
def get_bloaty_output(bloaty_args):
    bloaty_process_output = run("bloaty", bloaty_args)
    try:
        bloaty_output = bloaty_process_output.stdout.decode("utf-8")
    except Exception:
        print("Action:ERROR: Could not decode bloaty output:\n{}\n".format(bloaty_process_output.stdout), flush=True)
        sys.exit(1) # Exit with error code
    print(bloaty_output)
    return bloaty_process_output, bloaty_output


# -----------------------------------------------------------------------------
def add_to_gh_env_var(gh_env_var, key=None, value=None):
    """Adds a string to to a GH Action environmental variable."""
    if gh_env_var in os.environ:
        with open(os.environ[gh_env_var], 'a') as fh:
            if key:
                print("{}<<EOF".format(key), file=fh)
                print("{}".format(value), file=fh)
                print("EOF", file=fh)
            else:
                print("{}".format(value), file=fh)
    else:
        print("\nAction:WARN:", end=" ")
        print("Could not add to '{}' GH environmental variable.".format(gh_env_var))
        print("Key: {}, Value: {}".format(key, value))
        print(" " * 13 + "Are you sure this is running in a GH Actions environment?")


# -----------------------------------------------------------------------------
def add_dict_to_gh_env_var(gh_env_var, key, dict):
    jq_args = ["-n"]

    for k, v in dict.items():
        jq_args.append("--arg")
        jq_args.append(k)
        jq_args.append(str(v))
    jq_args.append('$ARGS.named')

    jq_process_output = run("jq", jq_args)
    if len(jq_process_output.stdout) < 3:
        print("\nAction:ERROR: The jq output is too short:\n{}\n".format(jq_process_output.stdout), flush=True)
        sys.exit(1)

    jq_encoded_output = str(jq_process_output.stdout)[2:-1]
    add_to_gh_env_var(gh_env_var, key, jq_encoded_output)


# -----------------------------------------------------------------------------
def create_encoded_output(bloaty_process_output, bloaty_output):
    # Add bloaty output to the GH Action outputs
    if DEBUG_INFO:
        print("\nAction:INFO: Adding bloaty output to GH Action output.", flush=True)
    add_to_gh_env_var("GITHUB_OUTPUT", key="bloaty-output", value=bloaty_output)

    if len(bloaty_process_output.stdout) < 3:
        print("\nAction:ERROR: The bloaty output is too short:\n{}\n".format(bloaty_process_output.stdout), flush=True)
        sys.exit(1)

    # ASCIIfy the byte string without the b''
    encoded_output = str(bloaty_process_output.stdout)[2:-1]
    add_to_gh_env_var("GITHUB_OUTPUT", key="bloaty-output-encoded", value=encoded_output)


# -----------------------------------------------------------------------------
def create_step_summary(action_summary, bloaty_process_output, bloaty_output):
    # Process any arguments specific to this script
    if action_summary or ("INPUT_OUTPUT-TO-SUMMARY" in os.environ and
            os.environ["INPUT_OUTPUT-TO-SUMMARY"] in ["true", "True", True, 1, "1"]):
        if DEBUG_INFO:
            print("\nAction:INFO: Adding bloaty output to GH Action workflow summary.", flush=True)
            print("             Action arg output-to-summary={}".format(os.environ["INPUT_OUTPUT-TO-SUMMARY"]))
        summary_title = os.environ.get("INPUT_SUMMARY-TITLE", default="bloaty output")
        add_to_gh_env_var(
            "GITHUB_STEP_SUMMARY",
            value="## {}\nFrom command: `{}`\n```\n{}\n```\n\n".format(
                summary_title, bloaty_process_output.args, bloaty_output
            )
        )


# -----------------------------------------------------------------------------
def create_summary_map(bloaty_file_args):
    # Get the bloaty output as CSV, so parsing is easier
    bloaty_csv_args_list = ["--csv"] + bloaty_file_args.split(" ")
    _, bloaty_csv_output = get_bloaty_output(bloaty_csv_args_list)
    output_lines = bloaty_csv_output.splitlines()

    if len(output_lines) < 2:
        print("\nAction:ERROR: The bloaty output contains not enough lines", flush=True)
        sys.exit(1)

    orig_vm_size = 0
    orig_file_size = 0
    current_vm_size = 0
    current_file_size = 0

    # Sum up the individual sizes to get the total diff / size
    for line in output_lines[1:]:
        line_split = line.split(",")

        try:
            # Case 1: Bloaty is called with a single file (no diff)
            if len(line_split) == 3:
                current_vm_size = current_vm_size + int(line_split[1])
                current_file_size = current_file_size + int(line_split[2])
            # Case 2: Bloaty is called with two files (diff)
            elif len(line_split) == 7:
                orig_vm_size = orig_vm_size + int(line_split[3])
                orig_file_size = orig_file_size + int(line_split[4])
                current_vm_size = current_vm_size + int(line_split[5])
                current_file_size = current_file_size + int(line_split[6])
            else:
                print("\nAction:ERROR: The bloaty output contains unexpected lines", flush=True)
                sys.exit(1)
        except ValueError:
            print("\nAction:ERROR: Could not convert the bloaty output parts to numbers", flush=True)
            sys.exit(1)

    # Depending on the bloaty call calculate the diff (with a meaningful percentage) or the total size
    file_absolute = current_file_size if orig_file_size == 0 else current_file_size - orig_file_size
    file_percentage = 0 if orig_file_size == 0 else file_absolute / orig_file_size * 100
    vm_absolute = current_vm_size if orig_vm_size == 0 else current_vm_size - orig_vm_size
    vm_percentage = 0 if orig_vm_size == 0 else vm_absolute / orig_vm_size * 100

    sum_map = {
        "file-percentage": f"{file_percentage:.2f}",
        "file-absolute": file_absolute,
        "vm-percentage": f"{vm_percentage:.2f}",
        "vm-absolute": vm_absolute
    }

    add_dict_to_gh_env_var("GITHUB_OUTPUT", key="bloaty-summary-map", dict=sum_map)


# -----------------------------------------------------------------------------
def main():
    # First check if we need to enable print of debug info
    global DEBUG_INFO
    if ("INPUT_ACTION-VERBOSE" in os.environ and
            os.environ["INPUT_ACTION-VERBOSE"] in ["true", "True", True, 1, "1"]):
        DEBUG_INFO = True

    # Parse the command line arguments
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--action-summary", action="store_true")
    parser.add_argument("--bloaty-file-args", required=True)
    parser.add_argument("--bloaty-additional-args")

    args = parser.parse_args()

    if DEBUG_INFO:
        print("\nAction:INFO: Python bloaty file args: {}".format(args.bloaty_file_args))
        print("Action:INFO: bloaty additional args:\n{}{}".format(args.bloaty_additional_args))
        print(flush=True)

    # Run bloaty with provided arguments
    bloaty_args_list = args.bloaty_additional_args.split(" ") + args.bloaty_file_args.split(" ")
    bloaty_process_output, bloaty_output = get_bloaty_output(bloaty_args_list)

    create_encoded_output(bloaty_process_output, bloaty_output)
    create_step_summary(args.action_summary, bloaty_process_output, bloaty_output)
    create_summary_map(args.bloaty_file_args)

    # Exit with success
    return 0


# -----------------------------------------------------------------------------
if __name__ == "__main__":
    sys.exit(main())

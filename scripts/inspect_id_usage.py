"""
Static ID usage scanner.

Finds suspicious usage patterns.

Read-only.
"""

import os
import re


PATTERNS = {

    "UUID assigned to FK":
        r"\.id\s*=\s*.*\.user_id",

    "Public ID used in query":
        r"filter.*user_id",

    "Internal ID in URL":
        r"url_for\(.*\.id",

    "Session storing internal ID":
        r"session\[.*user_id.*\].*=.*\.id",

    "Public ID in FK assignment":
        r"_id\s*=\s*.*\.public_id",
}


def scan():

    findings = []

    for root, _, files in os.walk("app"):

        for file in files:

            if not file.endswith(".py"):
                continue

            path = os.path.join(root, file)

            try:
                content = open(
                    path,
                    encoding="utf-8"
                ).read()

            except:
                continue


            for name, pattern in PATTERNS.items():

                matches = re.findall(
                    pattern,
                    content
                )

                if matches:

                    findings.append(
                        f"""
## {name}

File:
{path}

Matches:
{len(matches)}
"""
                    )


    os.makedirs(
        "reports",
        exist_ok=True
    )

    with open(
        "reports/id_usage_audit.md",
        "w"
    ) as f:

        f.write(
            "# ID Usage Audit\n"
        )

        f.write(
            "\n".join(findings)
        )


    print(
        "Created reports/id_usage_audit.md"
    )


if __name__ == "__main__":
    scan()
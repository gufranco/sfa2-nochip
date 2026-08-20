# Security

## Reporting

Report anything you believe is a security problem through
[GitHub's private vulnerability reporting](https://docs.github.com/code-security/security-advisories/guidance-on-reporting-and-writing/privately-reporting-a-security-vulnerability)
on this repository, rather than in a public issue. There is no service behind
this and no user data, so the realistic reports are about the supply chain and
about what a malformed input can make the code do.

## What is in scope

| Class | Example |
|-------|---------|
| Supply chain | A dependency or a pinned action that has been compromised |
| Malformed input | A crafted file that makes a reader allocate without bound, loop without end, or write outside where it was told |
| Path handling | An input that causes a write outside the directory the caller named |
| Digest handling | Anything that makes a verification pass when it should not |

## What is not

A conformance disagreement is a correctness bug and belongs in a normal issue.
So does a model that disagrees with real hardware. Neither is a security matter,
and filing them privately only slows the fix.

## What this repository will not do

It does not fetch a cartridge, a patch, or a microcode image, at build time or at
any other time. Any file it reads is one already on the machine
because somebody put it there. That is a deliberate limit rather than an
omission: a tool that fetches on your behalf is a tool that decides for you what
you are allowed to be given.

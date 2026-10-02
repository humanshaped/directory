# The Human Shaped directory

This is the list of software built by the
[Human-Shaped Principles](https://humanshaped.org/principles/), and
[humanshaped.org/apps](https://humanshaped.org/apps/) is where people
see it. I curate it myself, which is why it lives here as plain files
rather than in a database: anyone can read how it works, and every
change has a history.

## How an app gets listed

- **Built in a cohort?** It is listed when the cohort begins, and it
  grows on the site as you build.
- **Made from the [Universal App Template](https://github.com/bhwilkoff/UniversalAppTemplate)?**
  A nightly scan notices it and adds it to `candidates.json`, and I take
  a look.
- **Built another way, by the same principles?**
  [Ask to be listed](https://github.com/humanshaped/directory/issues/new?template=list-my-app.yml),
  and tell me about the human-shaped problem it solves.

Adding a `HUMAN-SHAPED.md` declaration to your repository (copy
[the template](https://github.com/bhwilkoff/UniversalAppTemplate/blob/main/docs/human-shaped/HUMAN-SHAPED-template.md))
helps in every case, because it says in your own words how your software
meets each principle.

## How it works

Each listing is one file in `apps/`, named for the app, and the words in
its `in_its_own_words` field come from the app itself. `tools/scan.py`
builds `directory.json` from those files, which the website reads. The
same script looks for public repositories that carry a declaration or
were made from the template, confirms each one with GitHub, and writes
them to `candidates.json`. GitHub has no way to ask which repositories
came from a template, so the scan looks for files only template-born
projects carry, and it can miss an app that removed them. A candidate is
never listed automatically.

The scan runs every night and whenever a listing changes. To run it
yourself: `python3 tools/scan.py` with a GitHub token in `GITHUB_TOKEN`.

Ben Wilkoff

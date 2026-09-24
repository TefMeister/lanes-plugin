# Check it yourself before you install

**Don't take our word that this plugin is safe. Have your own Claude Code check it.**

We can't do this check for you. A plugin's authors saying their own plugin is fine proves nothing,
and so does a safety check built into the plugin, because a bad plugin would simply report itself
clean. The check only means something when **someone else's Claude**, on **someone else's account**,
reads the raw files **before anything is installed or run**.

That is practical here: the plugin is plain readable text (instructions, small Python and shell
scripts, and hook files). No compiled programs are published in it. If an audit finds one, treat
that as a red flag.

## How

1. Open Claude Code in an empty folder on your own machine.
2. Paste the request below.
3. Note the version it reports, and install that same version. A check of one version says nothing
   about a later one, so check again when you update.

```
Before I install it, audit the Claude Code plugin marketplace at
https://github.com/TefMeister/lanes-plugin

Clone it into this folder and read every file in it. Do NOT install the plugin, and do not run
any of its scripts, hooks or commands.

Then tell me, in plain words:
1. Everything it would do on my machine: every hook (and when it fires), every script and
   command, which files it reads, writes or deletes, and which programs it runs.
2. Every link and web address in it: where each one goes, and whether that matches what the
   text around it says.
3. Anything that reaches the internet or could send data off my machine, and what data.
4. Anything hidden, obfuscated, encoded, compiled, or downloaded at run time.
5. Anything that asks for, reads or stores passwords, tokens, keys or other credentials.
6. Anything else that looks suspicious or does more than the README says it does.

Say how sure you are about each point. Finish with a clear verdict: safe to install or not,
and why, plus the version number (from plugins/lanes/.claude-plugin/plugin.json) you checked.
```

## Good to know

- Your Claude can be wrong, like any check. A careful read of plain text is still far better than
  trusting a stranger's README.
- The plugin's own tests are in `plugins/lanes/tools/tests/`. Your Claude may read them, but it
  should not need to run them to answer the questions above.
<!-- Deliberate: this is the security contact, and a page inviting people to audit the code
     needs somewhere for them to report what they find. It is also already public in every
     commit's author field, so hiding it here would achieve nothing.
     scrub-scan:allow -->
- Found something? Open an issue on this repository, or email **td3kxlvr@proton.me**.

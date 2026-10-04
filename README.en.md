# Darkroom Finish

**Describe the feeling. Let AI help with the edit.**

[中文](README.md) · English

Darkroom Finish is an AI photo-editing skill with a built-in photography reference library, designed to work with Codex. Pick a RAW photo and describe what you have in mind. It looks at the image, finds relevant references and techniques, then uses Photoshop / Camera Raw on your Mac to produce a first edit.

After seeing the result, you can keep the conversation going: “Make the colors more restrained.” “Keep the atmosphere in the shadows.” It uses your feedback to refine the edit, saving the settings and results for each version.

## Why it exists

Enjoying photography doesn't always mean enjoying hours of post-processing. Sometimes you know the feeling you want—a quieter image, a little more everyday warmth—but not which slider to reach for.

Darkroom Finish is built to help bridge that gap: choosing a direction, looking up techniques, doing the software work, and reviewing what actually changed.

You don't have to turn your ideas into a list of settings first. And you still decide whether the photograph feels right.

## What using it looks like

Once you've installed it and checked your setup, you can ask your assistant:

> Use darkroom-finish to edit this RAW photo. I'd like a quieter mood and more restrained colors, while keeping the original light and atmosphere. Look at what suits the image, then give me a first edit.

You don't need to arrive with a style in mind:

> I like this photo, but I'm not sure how to edit it. Tell me what's worth preserving, then suggest a direction and explain why it fits.

Start with a feeling, look at the first edit, then talk through the details. You can ask for specific changes—or say you prefer the original.

## Photography knowledge is part of the skill

The point isn't just to let AI operate Photoshop. It's to give the assistant something to consult before making decisions: what makes the light, color, or sense of space in a reference photograph work? Which ideas belong in this image, and which don't?

The open-source package includes:

- **195 photographer research files**, ranging from brief leads to more detailed notes on work and technique.
- **423 tutorial research notes**, covering editing approaches, possible techniques, and questions that still need checking.
- **40 reference directions across 10 scene categories**, helping the assistant choose based on the photograph rather than treating words like “cinematic” as a preset.

The library comes with the skill. You don't need access to the author's private collection. It contains research text, method notes, and source links—not a bundle of photographs, video courses, or photographer presets. Most of the research material is currently in Chinese; this English introduction is not a translation of the entire library.

This is a reference library, not a model trained to imitate 195 photographers. The material varies in depth and reliability, and 51 files still lack traceable source links. Research coverage isn't the same as a tested editing capability. [More about the library](https://github.com/pessiilee-eng/darkroom-finish/blob/main/docs/KNOWLEDGE-SCOPE.md)

## What happens behind the conversation

**Your photo + your idea → Look → Research → Plan → Edit locally → Review and refine**

1. **Look at the photograph first.** Understand its subject, light, colors, and what you want to preserve before choosing a style.
2. **Find references that fit.** Read relevant work studies and techniques, and decide what is useful. If a reference image can't be accessed, the assistant must say it's working from text alone.
3. **Turn the idea into adjustments.** Plan changes using supported controls for tone, white balance, color, curves, or local adjustments, and record the reasoning.
4. **Use the software on your Mac.** Photoshop / Camera Raw processes a working copy of the RAW file. The original stays untouched.
5. **Judge the image, not just the settings.** Review the whole photograph, before-and-after comparisons, and relevant details. Refine it with your feedback. The default limit is three attempts; limitations should be explained, not hidden behind endless retries.

The AI handles observation and planning, the library provides references, and local tools carry out the edit. You have the final say.

## Before you start

This version is for Mac users who already have Adobe software and want to try an AI-assisted editing workflow. You'll need:

- macOS with a working installation of Photoshop and Camera Raw.
- Codex, or an AI assistant that can read the skill, run local commands, and view images with your permission. Other assistants haven't been individually tested.
- Python 3.11 or later.

### Install and try your first photo

1. Download the public package from [Releases](https://github.com/pessiilee-eng/darkroom-finish/releases/latest) and extract the entire `darkroom-finish` folder. Don't copy just `SKILL.md`; the library and tools are part of the package.
2. In a new test project, place the whole folder at `.agents/skills/darkroom-finish/`. Don't overwrite an existing skill with the same name. If your assistant doesn't discover it automatically, ask it to read the folder's `SKILL.md`.
3. Ask the assistant to follow the [new-computer test guide](https://github.com/pessiilee-eng/darkroom-finish/blob/main/docs/TESTING.md), using the generated test image before opening a RAW photo you select. macOS may ask for permission to control Photoshop.

Keep working copies and editing results in a separate private workspace—not in the skill folder or a public GitHub repository. The linked technical guides are currently in Chinese.

<details>
<summary>Want to check the installation yourself? Show commands</summary>

Run these from the skill folder:

```bash
python3 -B scripts/darkroom.py doctor
python3 -B scripts/knowledge.py verify
python3 -B scripts/knowledge.py search "light"
python3 -B -m unittest discover -s tests -v
```

See the [local workflow guide](https://github.com/pessiilee-eng/darkroom-finish/blob/main/references/local-workflow.md) for execution details.

</details>

## Your photographs and privacy

Original RAW files and full-resolution exports stay on your computer. The tools don't upload them automatically. But **letting a cloud AI see a photo means sending a preview to that service**. That needs your permission and uses a resized, metadata-stripped preview—not the RAW file.

Results and settings are saved so you can compare versions, continue editing, and check what happened. Don't attach your private workspace to public issues. Local exports may still contain photo metadata, so check them separately before sharing.

## Something not working? Tell us

Please use [GitHub Issues](https://github.com/pessiilee-eng/darkroom-finish/issues). Chinese and English are both welcome. Check for an existing report first; otherwise, sign in to GitHub and select [New issue](https://github.com/pessiilee-eng/darkroom-finish/issues/new).

You don't need an error message to leave feedback. A confusing setup step, an edit that missed your intention, an incorrect source, or an awkward part of the workflow is worth reporting. Start your title with “Setup,” “Editing feedback,” “Knowledge correction,” or “Suggestion.”

Please include what you can:

- What you wanted to do and what you asked the assistant, with private details removed.
- What actually happened. For editing feedback, describe the specific mismatch: color, tone, or something important that wasn't preserved.
- The steps leading to the problem and whether it happens again.
- Your skill, macOS, Photoshop, and Camera Raw versions, plus the AI assistant you used. For setup problems, include your Python version if available.
- If there was an error, only the relevant lines after reviewing and removing sensitive information—not a full log or workspace.

**Issues are public. Start with text; don't upload private photographs, RAW files, full conversations, personal paths, or credentials.** If an image is essential, first discuss whether the issue can be reproduced with non-private test material you have permission to share publicly.

Reports help identify whether a problem comes from setup, image interpretation, reference selection, software execution, or result review. One person's preference for one photo shouldn't become a universal editing rule; workflow changes need reproduction and regression checks.

## What it doesn't promise

This release focuses on **editing and exploring a direction for one RAW photo at a time**. JPEG input isn't supported in this version. It doesn't offer generative fill, sky replacement, body reshaping, automatic skin retouching, or whole-library batch editing. It isn't a mobile editing app.

Some techniques in the library aren't connected to executable tools yet. A research note doesn't mean the skill can perform that technique. The public version has passed local Adobe tests with synthetic images, but testing on a second physical Mac and evaluating results on unseen photographs remain open. It won't necessarily get every photo right on the first attempt, or produce identical results on different computers. [Tests and known limitations](https://github.com/pessiilee-eng/darkroom-finish/blob/main/docs/RELEASE-STATUS.md)

Released under the [MIT license](https://github.com/pessiilee-eng/darkroom-finish/blob/main/LICENSE). Adobe software is not included; third-party photographs and tutorials remain the property of their respective rights holders.

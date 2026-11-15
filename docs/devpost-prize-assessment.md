# SpaceGit — prize selection and sponsor positioning

Team **ZygomorphicMereOtter**, Durham University, Skyline, table **203-N5**.
Prepared 15 November 2026. This assessment uses the prize descriptions supplied by
the team and the repository; it does not certify eligibility or submit an entry.

## Recommended approach

1. Keep the main DurHack submission focused on demonstrable execution, original
   product decisions and clear limitations. Overall awards are distinct from the
   sponsor category checkboxes supplied in the form; confirm the event's process.
2. Enter **Marshall Wace Challenge 1 — New Worlds**. The team confirmed the brief:
   “Make a project that explores the idea of New Worlds.” Position SpaceGit around
   exploring the past, present and possible arrangements of a familiar physical
   space, with human-reviewed evidence and independent 3D/projection tools.
3. Recommend **[MLH] DEV Writing Challenge** as the additional category supported
   by the supplied description. Review and publish [the DEV draft](dev-article-draft.md),
   then follow the challenge's entry instructions and retain its public URL.
   A draft in this repository alone does not complete that entry. Publication is
   pending and has not been performed by the assistant.

## Category assessment

| Category | Assessment for the current project |
| --- | --- |
| Marshall Wace Challenge 1 — New Worlds | Confirmed primary entry. SpaceGit explores new ways to understand and represent familiar spaces through reviewed image history, independent layout possibilities, 3D viewing and projection. |
| Marshall Wace Challenge 2 | Not selected; no brief or eligibility is inferred. |
| [MLH] DEV Writing Challenge | Recommended, conditional on publishing a useful technical post and following the actual entry rules. |
| Accenture / Waterstons / RS | Possible categories to investigate with sponsor staff. The provided list gives rewards but no brief; no eligibility or entry recommendation is established yet. |
| SGX FX Challenges 1 / 2 | Brief needed. The phrase Protect Your Assets is not enough to treat physical object history as an eligible financial/FX solution. |
| P&G / Neptune North / QRT challenges | Brief needed. Do not select based on sponsor name or generic AI use. |
| Best Use of Gemini API / ElevenLabs | No corresponding integration reported. Do not select for using OpenAI/Codex or local vision models. |
| Best Use of Entire | No demonstrated use of its Sessions/Graph/Brain/Trails capabilities. Ordinary Git plus Codex is not that integration. |
| Best Use of Solana | No Solana integration evidenced. |
| Best Use of Tiger Data | The application uses PostgreSQL; that does not establish Tiger Data use. No qualifying integration evidenced. |
| Best Use of Vultr | No Vultr deployment evidenced. |
| Best Use of MongoDB Atlas | PostgreSQL, SQLite and Silo do not establish MongoDB Atlas use. |

Do not add an unrelated dependency merely to collect a technology tag. The current
application already has a coherent local architecture and a useful technical story.

## Marshall Wace Challenge 1 — copy-ready positioning

“New worlds can begin in a familiar room. SpaceGit explores how a physical space
can become something we can inspect across time and imagine differently. Four
camera views produce an evidence-backed image history: AI proposes changes and
people decide which ones become approved revisions. Alongside that history,
independent layout branches, 3D viewing and projection tools let us explore spatial
representations and alternative arrangements. Our current achievement is making
observations and decisions traceable. Connecting approved image changes directly
to matching 3D point maps is the next step.”

This is our interpretation of the supplied theme; prize eligibility and judging
remain with the organizers. The supplied brief does not specify a required model,
API or sponsor service. Do not invent those requirements. Keep PointDiT generation,
YOLOE/DINOv2 perception, the simulated office and development assistance distinct.
The recorded smoke and contract tests are not a model-accuracy benchmark.

### Suggested demonstration arc

1. **The world we observe:** four source images and a real inference proposal.
2. **The world we approve:** human decision, selected commit and revision history.
3. **The worlds we explore:** independent metric layout branches, a model/PLY view
   and projector output. Identify simulation and any configured WSL generation.
4. **The bridge still to build:** explicit image-to-point correspondence for
   source-grounded 3D highlights. Do not present that future bridge as implemented.

## DEV Writing Challenge positioning

**Angle:** Why a room needs a review workflow before it needs an undo button.

**Technical substance:** camera-scoped identity, observed versus approved state,
atomic selected commits, provenance, integration boundaries, and the failed RLE
preview assumption caught by visual inspection.

**Original contribution to the article:** show the team's real diagrams, an actual
review card, one reproducible local workflow and a candid limitation. Credit the
pretrained models, libraries, collaborators and development assistance.

**Proposed entry description:** “A technical account of building SpaceGit, a
human-reviewed image history for physical spaces, including our local architecture,
model/evidence boundaries, integration lessons and what remains unfinished.”

## Sources and remaining information

- Prize descriptions and Challenge 1 selection/brief: supplied directly by the team
  in this chat, 15 November 2026.
- [DurHack official site](https://durhack.com/): identifies the 2026 event; it did
  not establish the two Marshall Wace briefs during preparation.
- [Project implementation record](implementation-status.md) and
  [submission copy](devpost-submission.md): evidence for feature claims.
- Still needed: public DEV URL after publication, demo-video URL and GoDaddy domain answer.
- Table row **N** is supplied by the team but absent from the originally pasted
  dropdown choices. Keep the true assignment; ask an organizer if the live form
  cannot represent it.

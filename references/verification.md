# Verification status

Release preparation was checked in a fresh virtual environment with an empty HOME and no private profile or API credentials: 122 tests and 83 subtests passed. Coverage includes real FFmpeg source-audio editing, narration evidence, event/SFX linkage, ducking, stale build/render/review rejection, configuration precedence and geometry input validation.

A synthetic two-second HTML project rendered through the public adapter and decoded completely at 1280×720, 30fps. Five sampled times matched across forward, reverse and cold-start seeks. A deliberately shortened timeline was rejected; the fixture was corrected without relaxing the checker. Changing the real HTML dependency or timeline invalidated the render receipt; restoring the timeline restored validity. No sample was submitted as aesthetic approval.

Both the public and the private local redaction hooks rejected real temporary commits containing their respective prohibited inputs; a neutral commit succeeded. The public file set and relative documentation links were checked before publication. Third-party license texts are retained; runtime packages and media are not bundled.

These tests establish only the behavior they exercise. They do not establish cinematic quality, voice suitability, complete upstream feature parity or success on every operating system. Known adapter limits: HyperFrames 0.8.72 and 30fps; explicit runtime/browser paths; absolute runtime receipts must be rebuilt after migration. Manual audiovisual review remains separate.

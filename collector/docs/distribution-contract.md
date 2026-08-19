# Independent Collector Distribution Contract

The public download and management surface is `https://memova.ai/collector`.

Release requirements:

- signed/notarized macOS package, signed Windows package, and documented Linux package;
- immutable version plus SHA-256 and signing identity for each artifact;
- links to the current Memova Privacy Policy and Terms of Service plus the Collector-specific
  Privacy Notice and User Agreement displayed before download, with the Collector-specific
  documents accepted again before first collection consent;
- installer plan, exact install target, rollback/uninstall path, and OS prerequisites;
- no dependency on files inside a Codex Plugin cache or marketplace checkout;
- browser Authorization Code + PKCE as the normal Collector login path;
- a local status interface that reads no conversation content;
- separate controls for consent, first preview, cloud connection, bounded acceptance, and scheduler
  activation;
- the exact Collector privacy/terms acceptance-bundle versions (which identify the incorporated
  general policies and Collector-specific documents) recorded in local consent and server consent;
  and
- download, privacy, terms, update, status, pause/resume, deletion, and uninstall links on the
  management page.

The plugin may link to this page and read content-free local status. It must not download an
installer, execute it, create an OAuth grant, or change scheduler state.

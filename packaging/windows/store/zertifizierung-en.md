# Notes for certification (NK-172)

Text für Partner Center → Submission options → Notes for certification.
Englisch, weil die Prüfer ihn lesen. Alles unterhalb der Linie einfügen.

---

NebenkostenFix is a free, open-source (GPL-3.0) desktop app for private landlords in Germany. It creates utility cost statements (Nebenkostenabrechnung) as PDF. The UI is German only.

No test account needed. Everything runs locally on this PC: there is no remote or publisher-operated server and no account with the publisher.
1. On first launch, the setup wizard asks for a user name and password. Any values work; they create a local login stored only on this PC.
2. A disclaimer dialog follows. Click "Verstanden" (Understood).
3. On the overview, click "Beispielimmobilie anlegen" (create sample property). It comes with a finished statement: open "Abrechnungen" in the left menu and click "PDF ansehen (detailliert)" to see the PDF.

runFullTrust: the app is a packaged Win32 program (Python, PyInstaller). It runs a web server bound to 127.0.0.1 only, protected by a per-launch token, and shows the UI in an Edge WebView2 window. It needs full trust for the local server, file dialogs (import, backup, PDF export) and its data folder in Documents\NebenkostenFix.

Requires the Microsoft Edge WebView2 Runtime (included in Windows 11 and current Windows 10).

Network: the Store version makes no network requests on its own. Its built-in updater is disabled when running as a package; updates come from the Store. Links (project page on GitHub, Ko-fi, "report a bug") open in the default browser only when the user clicks them.

Ko-fi is a voluntary donation link to the developer. Nothing in the app is sold or unlocked by it; all features are free.

Source code: https://github.com/Nerbry72/NebenkostenFix

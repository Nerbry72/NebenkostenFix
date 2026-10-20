# Release-Notizen

Je veröffentlichter Version eine Datei: `<SOFTWARE_VERSION>.md`, also
`0.17.0.md` für `SOFTWARE_VERSION = '0.17.0'`. Der Release-Workflow hängt sie
an den Installationsteil des GitHub-Release-Textes an.

**Sie ist Pflicht.** Ohne sie bricht der Release ab, und schon der Pull Request
nach `main` wird rot (`tests/test_release_notizen.py` und der Job
„Neue Versionsnummer"). Das ist Absicht: 0.16.0 ist ohne eine solche Datei
veröffentlicht worden, und der Release-Text bestand danach aus der
Installationsanleitung und einer einzigen Zeile mit dem PR-Titel — wer wissen
wollte, was neu ist, fand es dort nicht.

## Was hineingehört

Was ein Nutzer merkt, in seiner Sprache. Zwei Überschriften, mindestens eine
davon muss vorkommen:

```markdown
## Neu

**Kurzer Titel des Features** — #42
Zwei bis vier Sätze: was es kann, welche Einschränkung es hat, welche Nummer
oder welcher Paragraf dahintersteht. Das Issue als `#42` verlinken, wenn es
eines gibt.

## Behoben

**Was nicht ging, aus Sicht des Nutzers** — #42
Was passierte, woran es lag, was jetzt passiert.
```

Nicht hinein gehören Commit-Hashes, Branch-Namen, Phasennummern und interne
Befunde (B-01, K-01). Wer das sucht, liest den Pull Request.

Eine Datei ohne Nutzerwirkung — etwa ein reiner Umbau der Werkstatt — bekommt
trotzdem einen Satz, der genau das sagt. Nichts zu melden ist auch eine Meldung;
ein leerer Release-Text ist keine.

## Was der Workflow selbst beisteuert

Installationsanweisung für Windows und Docker, die Prüfsumme und die
Vergleichszeile zur Vorversion. Das steht nicht in dieser Datei.

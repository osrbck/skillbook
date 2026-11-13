# skillbook

Yapay zekâ kodlama ajanları için açık kaynak skill koleksiyonu. Her skill, açık
[Agent Skills](https://agentskills.io) formatında bir `SKILL.md` içeren bir klasördür; bu sayede
aynı skill **Claude Code**, **Codex**, **Antigravity** ve **Kiro**'da çalışır. Buradaki her skill dördü için yazılır ve
ajanın çalıştığı her yerde çalışır: masaüstü uygulaması, IDE ya da CLI.

> 🇬🇧 English: [README.md](README.md)

## Skill'ler

| Skill | Ne yapar | Komut |
|---|---|---|
| [**agentack**](skills/agentack/) | Her dilde ve mimaride full stack işler için conductor: projeyi bir kez okur, her görevi boyutlandırır ve Claude, Codex, Antigravity, Cursor ve Kiro arasında en küçük uzman ajan ekibine yönlendirir; contract ve review kapıları vardır. | `/agentack` |
| [**gitcommit**](skills/gitcommit/) | Çalışma klasöründeki değişiklikleri tek komutla birkaç temiz commit'e çevirir ve push'lar: amaca göre gruplar, deponun kendi kuralına ve diline uygun kısa mesajlar yazar, yalnızca senin adını kullanır (ortak yazar ya da yapay zekâ satırı yok), gizli anahtarları ve çöpleri dışarıda bırakır. Mesajları sağlayıcının en küçük güncel modeli yazar, bu yüzden çok az token harcar. Her git sunucusuyla çalışır. | `/gitcommit` |
| [**worklog**](skills/worklog/) | Belirli bir zaman aralığındaki yerel AI kodlama oturumlarını tarar ve yapılan işi proje bazında, süre tahminleri, commit'ler ve issue anahtarlarıyla raporlar. | `/worklog` |

Her skill'in klasöründe kendi README'si, değişiklik günlüğü ve katkı notları var.

## Kurulum

```bash
git clone https://github.com/osrbck/skillbook.git ~/skillbook
cd ~/skillbook

./install.sh                          # skill'leri listele
./install.sh worklog                  # tek skill, Claude Code için
./install.sh worklog agentack --all   # birden fazla skill; Claude Code, Codex, Antigravity ve Kiro için
./install.sh --everything --codex     # tüm skill'ler, Codex için
```

| Bayrak | Kurulduğu yer |
|---|---|
| *(yok)* ya da `--claude` | `~/.claude/skills/<skill>` (`CLAUDE_CONFIG_DIR`'e uyar) |
| `--codex` | `~/.codex/skills/<skill>` (`CODEX_HOME`'a uyar) |
| `--agy` | `~/.gemini/config/skills/<skill>` (Antigravity uygulama, IDE ve CLI) |
| `--kiro` | `~/.kiro/skills/<skill>` (Kiro IDE ve CLI; `KIRO_HOME`'a uyar) |
| `--all` | dördü birden |

Güncelleme: `git pull && ./install.sh <skill>...` · Kaldırma: `./install.sh <skill>... --uninstall`.
Sadece skill'in kendisi kopyalanır; README, changelog ve kurulum hook'ları repoda kalır.

**Gereksinimler:** Python 3.8+ ve bash; macOS, Linux ya da WSL. Skill'lerin yardımcı betikleri
sadece Python standart kütüphanesini kullanır.

## Repo yapısı

```
skillbook/
├── install.sh                  # tüm skill'ler için tek kurulum betiği
├── skills/
│   └── <skill>/
│       ├── SKILL.md            # zorunlu: name + description frontmatter, ardından talimatlar
│       ├── scripts/ …          # isteğe bağlı yardımcılar, referanslar, şablonlar
│       ├── README.md           # sadece repoda: GitHub'da görünen doküman
│       ├── CHANGELOG.md        # sadece repoda
│       └── install.hook.sh     # sadece repoda, isteğe bağlı: post_install / post_uninstall
├── tests/<skill>/              # skill bazında testler
├── docs/<skill>/               # görseller ve diğer doküman dosyaları
├── template/                   # yeni skill için başlangıç şablonu
└── scripts/validate.py         # her skill'in yapısını kontrol eder (CI'da çalışır)
```

## Geliştirme

```bash
python3 scripts/validate.py                               # tüm skill'lerin yapısı ve frontmatter'ı
python3 -m unittest discover -s tests/worklog -v          # tek skill'in testleri
for d in tests/*/; do python3 -m unittest discover -s "$d"; done   # hepsi
```

Yeni bir skill eklemek mi istiyorsun? [CONTRIBUTING.md](CONTRIBUTING.md)'ye bak.

## Lisans

[MIT](LICENSE). skillbook bir topluluk projesidir; Anthropic, OpenAI, Google, Cursor veya AWS ile
bağlantılı değildir.

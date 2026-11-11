# Agentack 2.0 — agentic stack

**Sözleşme odaklı modüler monolit projeler için, conductor yönetiminde çok sağlayıcılı ajan workflow'u.**

Claude Code, Codex ya da Antigravity'de `/agentack` yazınca oturumun bir *conductor*'a dönüşür: işi ölçer, işi
doğru bitirebilecek en küçük ekibi seçer ve her rolü zaten kullandığın ajan CLI'larındaki doğru
modele yönlendirir: Claude Code, Codex, Antigravity, Cursor, Kiro.

Desteklenen stack'ler: **Next.js · Angular · Node.js (TypeScript) · Go**.

> 🇬🇧 English: [README.md](README.md) · 0.1'den mi geliyorsun? Bkz. [0.1'den yükseltme](#01den-yükseltme).

<p align="center">
  <img src="../../docs/agentack/agentack-flow.tr.svg" alt="Agentack 2.0 ekibi: conductor uzman rollere dallanır, her rol S1–S4 seviyelerinden birine bağlıdır" width="100%">
</p>

## Öne çıkanlar

- **Tek sağlayıcı ya da birkaçı.** Roller modellere değil seviyelere bağlı. Tek sağlayıcı bütün
  workflow'u çalıştırır; iki üç sağlayıcı bağımsız review ve yedekleme ekler.
- **İşe göre ekip.** On rol var, çoğu iş ikisiyle biter, bir yazım hatası hiçbirini gerektirmez.
  Conductor önce ölçer; bir rolü ancak tetikleyicisi varsa çağırır.
- **Bağımsız review.** Birden fazla sağlayıcı varsa review, kodu yazandan farklı bir sağlayıcıda yapılır.
- **Her modele kendi dilinde brief.** Plan yapan modellere serbestlik, harfiyen uygulayan modellere
  adım adım talimat, mekanik modellere kural ve örnek. En güçlü modele sadece açık soru ve ucuz
  rollerin onun için topladığı kanıt gider.
- **Sormak yerine uyum sağlar.** Hesabında olmayan model atlanır: rol aynı seviyedeki başka bir
  sağlayıcıda, o seviye kimsede yoksa bir alt seviyede çalışır. Elinde olan model asla düşürülmez.
- **Limit bazlı model değişimi** (isteğe bağlı). Bir sağlayıcı kullanım limitine yaklaşınca aynı
  seviyedeki sıradaki sağlayıcı işi devralır; gerekirse görevin ortasında.
- **Öncelik sırası:** iş doğru bitsin, en az eforla bitsin, en az token harcansın.

## Hızlı başlangıç

```bash
git clone https://github.com/osrbck/skillbook.git ~/skillbook
~/skillbook/install.sh agentack --all   # Claude Code, Codex ve Antigravity; tek biri için: (bayraksız) --codex --agy
```

Ajanını yeniden başlat, sonra:

```
/agentack setup
```

Setup *senin* bilgisayarında neyin kurulu ve giriş yapılmış olduğuna bakar, sadece açıkta kalanı
sorar, her modeli tek kelimelik bir istekle dener ve bir eksik varsa tam olarak neyi düzeltmen
gerektiğini söyler. Sabit bir senaryosu yoktur, çünkü iki bilgisayarın kurulumu aynı olmaz.

## Komutlar

| Komut | Ne yapar |
|---|---|
| `/agentack <görev>` | İşi boyutlandırır, gereken ekibi çalıştırır, raporlar |
| `/agentack setup` | Bu bilgisayar için sağlayıcıları ve seçenekleri belirler; istediğin zaman tekrar çalıştır |
| `/agentack verify` | Her modeli ve sağlayıcıyı yeniden dener; düzelttiğin sağlayıcıyı geri getirir |
| `/agentack roster` | Kadro: rol, seviye, model, uygunluk puanı, yedekler |
| `/agentack limits` | Sağlayıcı başına kullanım ve şu an atlananlar |
| `/agentack doctor` | Sağlık kontrolü: CLI'lar, giriş, ortam, sonraki adımlar |
| `/agentack resume` | Yarım kalan işe devam eder; başka bir host'tan da olur |

```
/agentack billing modülüne fatura listeleme endpoint'i ve Next.js'te liste sayfası ekle
/agentack fatura boş durum metnindeki yazım hatasını düzelt
```

Yeni bir projede `/agentack Bu repoyu tara ve proje rehberini oluştur` ile başla. Rehber
(`CLAUDE.md` / `AGENTS.md`) uygulamaları, modülleri ve komutları tutar; skill'in varsayılanlarının
üstündedir. Conductor sadece sen istersen commit atar ya da PR açar.

## Seviyeler

| Seviye | Amaç | Roller | Claude | Codex | Antigravity |
|---|---|---|---|---|---|
| **S4** | geri dönüşü pahalı kararlar | decider | Fable | GPT-6 Astra | Gemini 4 Karbon, yoksa Argon |
| **S3** | plan ve kontrol | conductor, architect, reviewer | Opus | GPT-6.1 Sol (yüksek efor) | Gemini 4 Argon, yoksa 3.1 Pro |
| **S2** | inşa | be-go, be-node, fe-next, fe-angular, qa | Sonnet | GPT-6.1 Sol (orta efor) | Gemini 3.1 Pro |
| **S1** | mekanik iş | scout, contract-guard | Haiku | GPT-6 Luna | Gemini 3.8 Flash |

Cursor (Composer, Auto) ve Kiro (Auto) S1 ve S2'yi karşılar; review ve karar rolleri herhangi bir
sağlayıcıdaki adı belli bir modeli tercih eder. Bunlar varsayılanlardır: kadronda gerçekte ne
olduğu hesaplarına bağlıdır ve `/agentack roster` ile görülür.
Ayrıntı: [`providers.md`](skills/agentack/references/providers.md).

## Güçlü yönler

Seviye bir modelin ne kadar yetenekli olduğunu söyler; güçlü yönler bir sağlayıcının neyde iyi
olduğunu. Her sağlayıcı iş türü başına 1–5 arası puanlanır ve kadro onu iyi yaptığı işte tutar.

| Sağlayıcı | karar | plan | review | görsel | backend | frontend | test | mekanik |
|---|---|---|---|---|---|---|---|---|
| Claude Code | 5 | 5 | 5 | 4 | 5 | 4 | 5 | 4 |
| Codex | 5 | 4 | 4 | 4 | 4 | 4 | 4 | 3 |
| Antigravity | 4 | 4 | 4 | 5 | 2 | 2 | 2 | 2 |

Sırayı senin sağlayıcı önceliğin belirler; iki düzeltme uygulanır: bir iş türünde zayıf puanlı
(2 ve altı) sağlayıcı o işi ancak son çare olarak yapar, görsel review gibi uzmanlık işleri de en
yüksek puanlıya gider. Yani Gemini plan yapar, review yapar, arayüzü kontrol eder; ama kodu ancak
başka seçenek yoksa yazar. Setup, seçim yapmadan önce bu tabloyu gösterir; `--rate` ile her puan
değiştirilebilir. Puanların tarihi ve dayanakları:
[`strengths.md`](skills/agentack/references/strengths.md).

## Brief stilleri

| Modeller | Brief'te ne olur |
|---|---|
| Opus ve dengi (S3) | hedef, bağlam, kısıtlar, "bitti" neye benzer |
| Sonnet ve dengi (S2) | adı belli dosyalar, adımlar, çıktı biçimi, sınırlar |
| GPT-6.1 Sol, Auto yönlendiriciler | sırayla her adım, hiçbir şey örtük değil |
| Fable, GPT-6 Astra, Gemini 4 Karbon (S4) | açık soru ve kanıt, bir meslektaşa sorar gibi |
| Haiku, GPT-6 Luna, Gemini 3.8 Flash (S1) | girdi/çıktı örnekli kesin kurallar, küçük partiler, örnekleme kontrolü |

Conductor, rol hangi modelde çalışıyorsa ona uygun şablonu alır. En güçlü model sadece üç noktada
çağrılır: geri dönüşü pahalı bir karar, o karara ikinci görüş ve iki başarısız denemeden sonraki
eskalasyon.

## Yollar

| Yol | Ne zaman | Ekip |
|---|---|---|
| **Direkt** | en fazla 2 dosya, yeri belli, contract/şema/auth etkisi yok, bir komutla doğrulanabiliyor | sadece conductor |
| **Hızlı** | tek modül, tek katman, contract değişmiyor | bir builder → reviewer |
| **Standart** | contract değişiyor, 2 modül, 5'ten fazla dosya ya da sebep belirsiz | architect → contract kapısı → builder'lar → reviewer (gerekirse qa) |
| **Ağır** | yeni modül, şema değişikliği, auth/ödeme, kırıcı contract | decider (+ ikinci görüş) → Standart ekip + qa |

İki kapı hiç esnemez: **contract kontrolü geçmeden inşa başlamaz** ve **bağımsız review olmadan
iş bitmiş sayılmaz** (Direkt yol hariç). İş ölçülenden geniş çıkarsa conductor onu bir üst yola
taşır. Ayrıntı: [`sizing.md`](skills/agentack/references/sizing.md).

## Modeller ve limitler

**Eksik modeller** her zaman otomatik ele alınır: hesabında olmayan model (listede yoksa, `verify`
reddederse ya da çalışma sırasında reddedilirse) atlanır ve hatırlanır.

**Kullanım limitleri** değişim açıkken ele alınır:

- Bir sağlayıcı limit bildirdiğinde (sıfırlanma saatine kadar) ya da ölçülen kullanım eşiği
  geçtiğinde (varsayılan %85) atlanır. Kullanım Codex, Kiro, Antigravity (deneysel) ve isteğe
  bağlı durum çubuğu kancasıyla Claude Code için ölçülür.
- Önce aynı seviye. Builder'lar son çare olarak bir seviye düşebilir. Reviewer, decider ve
  architect limit yüzünden asla düşürülmez: iş durur ve ne zaman sıfırlanacağını söyler.
- Limit yüzünden yarıda kalan görevi sıradaki sağlayıcı aynı çalışma klasöründen devralır.
- Çalışma sırasında soru sorulmaz. Her değişim kapanış raporunda yazar.

## Nasıl çalışır

```
/agentack → conductor (Claude Code, Codex ya da Antigravity oturumun)
               │  ölç → boyutlandır → yol → kapılar
               ▼
            agentack.py dispatch ── rol → seviye → sağlayıcı + model
               ├─ claude -p · codex exec · agy -p · agent -p · kiro-cli chat --no-interactive
               └─ Claude Code'da Claude işçileri yerel alt ajan olarak çalışır
```

- İşçiler reponda dar bir brief'le, arayüzsüz çalışır ve asla commit atmaz.
- Salt-okur roller mümkün olan yerde CLI tarafından zorlanır, her çalıştırmadan sonra `git status` ile doğrulanır.
- Çalıştırmalar, kayıtlar ve brief'ler `<proje>/.agentack/` altında durur (git'e girmez).
- Yardımcı script saf Python'dır, bağımlılığı yoktur. Sadece bilgisayarındaki ajan CLI'larıyla konuşur.
- Bir proje, `.agentack.json` dosyasını commit ederek sağlayıcıları kısıtlayabilir: `{"allowed_providers": ["claude"]}`.

Agentack **sözleşme odaklı modüler monolit** varsayar ve bunu korumaya yardım eder: modüller kendi
verisinin sahibidir ve dar bir public yüzey açar; contract'lar (OpenAPI 3.1, AsyncAPI 3, RFC 9457
hataları) `contracts/<modül>/` altında durur ve kod onlardan üretilir. Bkz.
[`architecture.md`](skills/agentack/references/architecture.md) ve
[`contracts.md`](skills/agentack/references/contracts.md).

## Gereksinimler

- **Conductor:** Claude Code, Codex ya da Antigravity (uygulama, IDE ya da CLI), plan ve kontrol
  sınıfı bir modelde (Opus, GPT-6.1 Sol, Gemini 4 Argon ya da üstü). Daha küçük bir modelde
  Agentack uyarır ve devam etmeden önce onay ister. Kiro'nun conductor olması planlanıyor;
  şimdilik sağlayıcı olarak çalışıyor.
- **Sağlayıcılar:** Claude Code, Codex, Antigravity (`agy`), Cursor CLI, Kiro CLI'dan en az biri.
- Python 3.8+ ve git; macOS, Linux ya da WSL. Projen bir git reposu olmalı.

Güncelleme: `cd ~/skillbook && git pull && ./install.sh agentack --all` · Kaldırma: `./install.sh agentack --uninstall`.

### 0.1'den yükseltme

2.0, sadece Claude ile çalışan 0.1'in yerini aynı ad ve komutla alır. `install.sh agentack` yeni skill'i
eskisinin üstüne kurar ve 0.1'in `~/.claude/agents/` altına koyduğu on global alt ajanı
`~/.claude/backups/` altına taşır (2.0 rol talimatlarını skill'in içinde tutar, global bir şeye
gerek kalmaz). Sonra bir kez `/agentack setup` çalıştır. 0.1 için yazılmış proje rehberleri
çalışmaya devam eder.

## Durum

| Sağlayıcı | Durum |
|---|---|
| Claude Code | gerçek CLI ile test edildi |
| Codex, Antigravity, Cursor, Kiro | her CLI'ın dokümanına göre yazıldı, simülasyon testlerinden geçiyor |

Model adları ve CLI bayrakları sık değişiyor. `/agentack verify` senin bilgisayarında neyin
çalıştığını kanıtlar; orada gördüklerini bildirirsen çok yardımcı olur.

Katkılar için [CONTRIBUTING.md](CONTRIBUTING.md) · Lisans: [MIT](../../LICENSE).

Agentack bir topluluk projesidir; Anthropic, OpenAI, Google, Cursor veya AWS ile bağlantılı değildir.

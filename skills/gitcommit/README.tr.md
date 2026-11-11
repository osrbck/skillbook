# gitcommit

**Çalışma klasöründeki değişiklikleri temiz commit'lere çevirir ve push'lar; üzerinde yalnızca
senin adın olur.** `/gitcommit` neyin değiştiğini okur, değişiklikleri amacına göre birkaç
commit'e ayırır, deponun kendi kuralına uygun kısa mesajlar yazar ve projenin bağlı olduğu
sunucuya gönderir.

> 🇬🇧 English: [README.md](README.md)

```
/gitcommit
```

```
origin/main'e 3 commit gönderildi
a1b2c3d fix(cart): round totals per line
d4e5f6a feat(cart): add coupon support
0a9b8c7 chore: bump dependencies
Dışarıda bırakılanlar: .env (kimlik bilgisi dosyası) · debug.log (.gitignore'a ait)
```

## Ne yapar

- **Bütün çalışma klasörü, kim değiştirmiş olursa olsun.** Son commit'ten farklı olan her şeyi
  tarar: bu oturumdaki, önceki bir oturumdaki, başka bir ajanın yaptığı ya da elle yazılmış
  değişiklikler. Değişikliğin ne zaman ve nerede yapıldığı önemli değildir.
- **Her commit tek bir amaç.** Bir özellik, testleri ve belgeleriyle birlikte girer; düzeltme,
  refactor, bağımlılık güncellemesi ve biçimlendirme ayrı commit olur. Birkaç oturumda birikmiş
  iş, olması gereken commit'lere bölünür. Çoğu zaman 1–5 commit.
- **Önce geçmişi okur.** Yeni commit'ler son commit'lerin devamıdır: aynı türler, kapsamlar ve
  kelimeler. Düzeltme yeni bir `fix` commit'i olur; var olan commit'ler asla değiştirilmez.
- **Görev ve commit tek çağrıda.** `/gitcommit`'in ardına görevi yazarsan ajan işi yapar, son
  adım olarak commit'ler ve gönderir. Bitmemiş ya da testi geçmeyen iş gönderilmez.
- **Senin kuralın.** Son 50 commit'i okur ve bulduğuna uyar: kendi tür ve kapsamlarınla
  Conventional Commits, gitmoji, iş numarası öneki ya da düz cümle. Yeni depoda Conventional
  Commits kullanır.
- **Kısa mesajlar.** Yaklaşık 50 karakterlik (en çok 72), emir kipinde, noktasız bir başlık.
  Gövde yalnızca kırıcı bir değişiklik ya da diff'ten anlaşılamayacak bir neden varsa yazılır;
  o zaman da en çok üç satır.
- **Yalnızca senin adın.** `Co-authored-by` yok, "Generated with …" yok, araç ya da model adı
  yok. Yazar ve commit'leyen, `git config`'te kim yazıyorsa odur; ajanın ortamı başka bir şey
  ayarlasa bile.
- **Özel olan içeri girmez.** Eklenen satırlardaki anahtar ve token'lar, yeni kimlik bilgisi
  dosyaları (`.env`, `*.pem`, `id_rsa` …), çözülmemiş çakışma işaretleri, 5 MB'tan büyük yeni
  dosyalar ve çöpler (`node_modules`, `.DS_Store`, önbellekler) dışarıda bırakılır ve listelenir.
- **Sunucu fark etmez.** GitHub, GitLab, Bitbucket ya da kendi sunucun: projenin zaten bağlı
  olduğu uzak depoya düz bir `git push` yapar. Yeni dal aynı adla yayımlanır.
- **Bağlantı yoksa.** Uzak depo yoksa yalnızca yerelde commit atar ve nasıl ekleneceğini söyler.
  Klasör henüz bir depo değilse önce `git init` çalıştırır.

## Asla yapmadıkları

Zorla push · hook'ları atlamak (`--no-verify`) · çağrıdan önce var olan commit'leri değiştirmek
· dal değiştirmek, stash'lemek ya da işini silmek · git ayarlarını ya da uzak depoları
değiştirmek · kendiliğinden pull, rebase ya da merge. Uzak depoda sende olmayan commit'ler varsa
durur ve bunu söyler; commit'lerin yerelde kalır.

## Nasıl çalışır

```
/gitcommit
   │
   ├─ 1. inspect   ne değişti, son commit'ler, bu depo onları nasıl yazıyor,
   │               ne dışarıda kalmalı
   ├─ 2. ajan diff'leri okur, amaca göre gruplar ve başlıkları yazar
   ├─ 3. commit    grup başına bir çağrı; kuralı bozan mesaj, hiçbir şey yazılmadan reddedilir
   │               (ortak yazar satırı, uzunluk, başkasının imzası)
   └─ 4. push      bu çağrıda atılan her commit yeniden denetlenir, sonra gönderilir; asla zorla değil
```

Gruplama ve ifade ajanın işidir. Kurallar ise koddur: commit'i ve push'u küçük bir Python
yardımcısı (yalnızca standart kütüphane) yapar, bu yüzden her ajanda aynı şekilde geçerlidir.

## Kurulum

Gereksinimler: git, Python 3.8+ ve Claude Code, Codex ya da Antigravity. macOS, Linux ve WSL.

```bash
git clone https://github.com/osrbck/skillbook.git ~/skillbook
~/skillbook/install.sh gitcommit          # Claude Code
~/skillbook/install.sh gitcommit --codex  # Codex
~/skillbook/install.sh gitcommit --all    # Claude Code, Codex ve Antigravity
```

Kurulum, commit'lerinin taşıyacağı adı ve e-postayı gösterir. Güncellemek için
`cd ~/skillbook && git pull && ./install.sh gitcommit`, kaldırmak için
`./install.sh gitcommit --uninstall`.

## Kullanım

```
/gitcommit                      değişen her şey → commit'ler → push
/gitcommit pushlama             yalnızca commit
/gitcommit staged               yalnızca stage'lediklerin, tek commit olarak
/gitcommit tek commit           her şey için tek commit
/gitcommit plan                 atacağı commit'leri gösterir; hiçbir şeyi değiştirmez
/gitcommit include .env.test    işaretlenmiş bir dosyayı da commit'ler
/gitcommit türkçe               geçmiş hangi dilde olursa olsun bu dilde yazar
/gitcommit kupon özelliği       klasörde zaten duran işe dair ipucu
/gitcommit ödeme sayfasına kupon desteği ekle
                                görev: işi yapar, sonra commit'ler ve gönderir
```

Yalnızca sen çağırdığında çalışır. Yol boyunca soru sormaz; yalnızca commit'i engelleyen bir şey
varsa durur: `user.name` / `user.email` yoksa, yarım kalmış bir merge ya da rebase varsa,
çözülmemiş çakışma varsa, HEAD bir dala bağlı değilse.

## Mesajlar

| Deponun geçmişi | Yazdığı başlık |
|---|---|
| Conventional Commits | `fix(cart): round totals per line` (senin tür ve kapsamlarınla) |
| gitmoji | geçmişin nasıl yazıyorsa |
| iş numarası öneki | `SHOP-42 Round totals per line` (geçmişin nasıl yazıyorsa) |
| düz cümleler | `Round cart totals per line` |
| henüz yok | Conventional Commits |

**Dil, söylemene gerek kalmadan geçmişi izler.** Eski commit'lerin Türkçeyse yenileri de Türkçe
olur (`feat(sepet): kupon desteği ekle`); İngilizceyse İngilizce. Ajanla hangi dilde konuştuğun
fark etmez. Yeni depoda İngilizce yazar; çağrıda belirttiğin dil (`/gitcommit türkçe`) her zaman
önceliklidir. Fiil biçimi de geçmişe uyar (`ekle` ya da `eklendi`). Dal
adındaki iş numarası yalnızca geçmişin zaten kullandığı biçimde yazılır. `Signed-off-by`,
yalnızca geçmişi bunu kullanan depolarda ve senin adına eklenir.

## Claude Code ve ortak yazar satırı

Claude Code commit'lere varsayılan olarak `Co-Authored-By` satırı ekler. Bu skill kendi
commit'lerinde bunu geçersiz kılar ve bu satırı taşıyan her mesajı reddeder. Bunu her yerde, bu
skill'in dışında da kapatmak için `~/.claude/settings.json` dosyasına şunu ekle:

```json
{
  "attribution": { "commit": "", "pr": "", "sessionUrl": false }
}
```

## Yardımcıyı elle çalıştırmak

```bash
G="python3 ~/.claude/skills/gitcommit/scripts/gitcommit.py"
$G inspect                                             # değişiklikler, stil, işaretler, engeller (JSON)
$G commit --subject 'fix: handle empty carts' -- src/cart
$G check --since <commit>                              # yazar, mesaj ve ortak yazar denetimi
$G push --since <commit>                               # denetler, sonra gönderir; asla zorla değil
```

## Gizlilik

Yardımcı, git'i kendi bilgisayarında çalıştırır ve push sırasında yalnızca senin uzak deponla
konuşur. Başka hiçbir ağ isteği yapmaz. Ajan, işi adlandırmak için ihtiyaç duyduğu diff'leri
okur; bunlar o ajanla konuşmanın parçası olur. İşaretlenen gizli anahtarlar türü ve satırıyla
bildirilir, değeri asla yazılmaz.

## Lisans

[MIT](../../LICENSE). gitcommit bir topluluk projesidir; Anthropic, OpenAI, Google, GitHub ya da
GitLab ile bağlantısı yoktur.

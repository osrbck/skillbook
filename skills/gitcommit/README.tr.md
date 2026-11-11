# gitcommit

**Çalışma klasöründeki değişiklikleri temiz commit'lere çevirir ve push'lar; üzerinde yalnızca
senin adın olur ve bunu çok az token'la yapar.** `/gitcommit` tek bir komut çalıştırır. Yardımcı
betik neyin değiştiğini tarar, kullandığın sağlayıcının en küçük güncel modeli commit mesajlarını
yazar ve sonuç projenin bağlı olduğu sunucuya gönderilir. Konuştuğun ajan yalnızca raporu yazar.

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

**Claude Code, Codex, Antigravity ve Kiro**'da çalışır.

## Ne yapar

- **Bütün çalışma klasörü, kim değiştirmiş olursa olsun.** Son commit'ten farklı olan her şey
  kapsamdadır: bu oturumdaki, önceki bir oturumdaki, başka bir ajanın yaptığı ya da elle yazılmış
  değişiklikler.
- **Her commit tek bir amaç.** Bir özellik, testleri ve belgeleriyle birlikte girer; düzeltme,
  refactor, bağımlılık güncellemesi ve biçimlendirme ayrı commit olur. Birkaç oturumda birikmiş
  iş, olması gereken commit'lere bölünür.
- **Senin kuralın ve senin dilin.** Yakın geçmişi okur ve onu sürdürür: kendi tür ve
  kapsamlarınla Conventional Commits, gitmoji, iş numarası öneki ya da düz cümle. Geçmiş
  Türkçeyse mesajlar Türkçe, İngilizceyse İngilizce olur. Yeni depoda İngilizce Conventional
  Commits kullanır.
- **Kısa mesajlar.** Yaklaşık 50 karakterlik (en çok 72), noktasız bir başlık. Gövde yalnızca
  kırıcı bir değişiklik ya da diff'ten anlaşılamayacak bir neden varsa yazılır.
- **Yalnızca senin adın.** `Co-authored-by` yok, "Generated with …" yok, araç ya da model adı
  yok. Yazar ve commit'leyen, `git config`'te kim yazıyorsa odur.
- **Özel olan içeri girmez ve hiçbir modele gösterilmez.** Eklenen satırlardaki anahtar ve
  token'lar, yeni kimlik bilgisi dosyaları (`.env`, `*.pem`, `id_rsa` …), çözülmemiş çakışma
  işaretleri, 5 MB'tan büyük yeni dosyalar ve çöpler (`node_modules`, `.DS_Store`, önbellekler)
  model hiçbir şey görmeden önce ayıklanır, commit'lerin dışında bırakılır ve raporda listelenir.
- **Sunucu fark etmez.** Projenin zaten bağlı olduğu uzak depoya düz bir `git push`: GitHub,
  GitLab, Bitbucket ya da kendi sunucun. Uzak depo yoksa yalnızca yerelde commit atar; klasör
  henüz bir depo değilse önce `git init` çalıştırır. Kendiliğinden parola penceresi açmaz.
- **Görev ve commit tek çağrıda.** `/gitcommit ödeme sayfasına kupon desteği ekle` işi senin
  seçtiğin modelle yapar, sonra küçük modelle commit'leyip gönderir.

## Az token, en küçük güncel modelle

Commit mesajı yazmak, asıl işini yaptığın modeli gerektirmez. Öncelik sırası **görev, bağlam,
token**: commit'ler doğru olmalı, model onları doğru adlandırmaya yetecek kadarını görmeli; geri
kalan her şey ancak ondan sonra kısılır.

| Bulunduğun yer | Planı yazan |
|---|---|
| Claude Code | güncel Haiku (`haiku` takma adı) |
| Codex | hesabının listelediği en yeni Luna (yoksa nano / mini) |
| Antigravity | hesabının listelediği en yeni Flash-Lite, yoksa en hafif eforda Flash |
| Kiro | listelediği en yeni Haiku sınıfı model, yoksa en düşük oranlı modeli, yoksa Auto |

Model, sağlayıcının kendi CLI'ından model listesi istenerek bulunur; yeni bir sürüm çıktığında
burada güncelleme gerekmez. `GITCOMMIT_MODEL=<model>` ile değiştirebilirsin.

- **Ana modelin** 4 KB'tan küçük bir skill dosyası okur, tek bir komut çalıştırır ve birkaç satır
  yazar. Diff okumaz.
- **Küçük model** sağlayıcının CLI'ı üzerinden bir kez çağrılır; aracı, izni yoktur ve boş bir
  klasörde çalışır. Kuralları, yakın geçmişi, değişiklik listesini ve sınırlı bir diff'i alır
  (kilit, üretilmiş ve ikili dosyalar yalnızca adıyla) ve JSON bir planla cevap verir.
- **Yardımcı betik** gerisini düz kodla yapar: planı denetler (her yol tam bir kez, mesaj
  kuralları), yanlışsa bir kez geri gönderir, commit'ler, push'lar ve raporu yazar.
- Sağlayıcının CLI'ı yoksa ya da başarısız olursa planı aynı özetten ana modelin yazar; iş her
  durumda tamamlanır.

## Asla yapmadıkları

Zorla push · hook'ları atlamak (`--no-verify`) · çağrıdan önce var olan commit'leri değiştirmek
· dal değiştirmek, stash'lemek ya da işini silmek · git ayarlarını ya da uzak depoları
değiştirmek · kendiliğinden pull, rebase ya da merge · parola ya da token istemek. Uzak depoda
sende olmayan commit'ler varsa durur ve bunu söyler; commit'lerin yerelde kalır.

## Kurulum

Gereksinimler: git, Python 3.8+ ve Claude Code, Codex, Antigravity ya da Kiro'dan biri (CLI'ı
PATH'te olursa yazma işini küçük model yapar). macOS, Linux ve WSL.

```bash
git clone https://github.com/osrbck/skillbook.git ~/skillbook
~/skillbook/install.sh gitcommit          # Claude Code
~/skillbook/install.sh gitcommit --codex  # Codex (ayrıca: Antigravity için --agy, Kiro için --kiro)
~/skillbook/install.sh gitcommit --all    # dördü birden
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
/gitcommit include .env.test    dışarıda bırakılmış bir dosyayı da commit'ler
/gitcommit türkçe               geçmiş hangi dilde olursa olsun bu dilde yazar
/gitcommit sor                  oturum eksikse sisteminin parola penceresinin sormasına izin verir
/gitcommit kupon özelliği       klasörde zaten duran işe dair ipucu
/gitcommit ödeme sayfasına kupon desteği ekle
                                görev: işi yapar, sonra commit'ler ve gönderir
```

Yalnızca sen çağırdığında çalışır, yol boyunca soru sormaz ve rapordan başka bir şey söylemez.
Yalnızca commit'i engelleyen bir şey varsa durur: `user.name` / `user.email` yoksa, yarım kalmış
bir merge ya da rebase varsa, çözülmemiş çakışma varsa, HEAD bir dala bağlı değilse.

## Mesajlar

| Deponun geçmişi | Yazdığı başlık |
|---|---|
| Conventional Commits | `fix(cart): round totals per line` (senin tür ve kapsamlarınla) |
| Türkçe geçmiş | `feat(sepet): kupon desteği ekle` |
| gitmoji | geçmişin nasıl yazıyorsa |
| iş numarası öneki | `SHOP-42 Round totals per line` (geçmişin nasıl yazıyorsa) |
| düz cümleler | `Round cart totals per line` |
| henüz yok | İngilizce Conventional Commits |

`Signed-off-by`, yalnızca geçmişi bunu kullanan depolarda ve senin adına eklenir.

## Sunucu oturum isterse

Ajanın kabuğu her zaman senin oturum açtığın yerde oturum açmış değildir. Bir proje IDE'nde ya
da bir masaüstü uygulamasında bağlı olabilir ama düz `git push` için oturumu olmayabilir. Bu
durumda git, masaüstünün parola programına düşer ve çalışmanın ortasında bir kullanıcı adı ve
şifre penceresi açar. gitcommit buna izin vermez. Commit'ler atılır, push durur ve nedenini
seçeneklerinle birlikte görürsün:

```
4 commit atıldı; push durdu: bu ortamda github.com için kayıtlı oturum yok
1. Bu makinedeki SSH anahtarını kullan: git remote set-url origin git@github.com:sen/app.git
2. Parola pencerenin sormasına izin ver: skill'i `sor` ile yeniden çağır
3. Git için oturumu kendin kaydet: kendi terminalinde bir kez `git push` çalıştır
```

Git için bilerek kurduğun her şey olduğu gibi kullanılır: kimlik yardımcıları, `GIT_ASKPASS`,
`core.askPass`, SSH anahtarları ve ajanları.

## Claude Code ve ortak yazar satırı

Claude Code commit'lere varsayılan olarak `Co-Authored-By` satırı ekler. Bu skill bunu asla
yapmaz ve bu satırı taşıyan her mesajı reddeder. Bunu her yerde, bu skill'in dışında da kapatmak
için `~/.claude/settings.json` dosyasına şunu ekle:

```json
{
  "attribution": { "commit": "", "pr": "", "sessionUrl": false }
}
```

## Yardımcıyı elle çalıştırmak

```bash
G="python3 ~/.claude/skills/gitcommit/scripts/gitcommit.py"
$G run --host claude              # işin tamamı; yalnızca planı görmek için --dry-run ekle
$G run --host codex --json        # ayrıntılarla: kullanılan model, commit'ler, push sonucu
$G inspect                        # değişiklikler, stil, işaretler, engeller (JSON)
$G commit --subject 'fix: handle empty carts' -- src/cart
$G push --since <commit>          # denetler, sonra gönderir; asla zorla değil
```

## Gizlilik

Yardımcı, git'i kendi bilgisayarında çalıştırır ve push sırasında yalnızca senin uzak deponla
konuşur. Küçük modele, zaten kullandığın sağlayıcının CLI'ı ve mevcut oturumunla ulaşılır; ona
commit geçmişi başlıkları, değişen yollar ve sınırlı bir diff gönderilir, işaretlenmiş bir yol
asla gönderilmez. Push oturum eksikliğinden reddedilirse yardımcı aynı sunucuya bir kez SSH
anahtarını kabul edip etmediğini sorar (`ssh -T`). Başka hiçbir ağ isteği yapmaz; hiçbir kimlik
bilgisini okumaz ya da saklamaz.

## Lisans

[MIT](../../LICENSE). gitcommit bir topluluk projesidir; Anthropic, OpenAI, Google, AWS, GitHub
ya da GitLab ile bağlantısı yoktur.

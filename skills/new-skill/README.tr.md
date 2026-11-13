# new-skill

**Bir görevi ya da az önceki oturumu, tekrar çağırabileceğin bir skill'e çevirir.** `/new-skill`
skill'in ne olacağını bulur, nasıl kuracağını sana sorar, yazar, denetler ve kullandığın
ajanlara kurar.

> 🇬🇧 English: [README.md](README.md)

```
/new-skill search skilli oluştur, derin aramalar yapsın
```

```
/new-skill
```

**Claude Code, Codex, Antigravity ve Kiro**'da çalışır; hangisinden çağırırsan çağır.

## Ne yapar

- **Görevden.** `/new-skill`'den sonra skill'in ne yapacağını yaz. Oturumda o konuda ne varsa
  (verilen kararlar, çalışan komutlar, yaptığın düzeltmeler) skill'e girer.
- **Oturumdan.** Hiçbir şey yazmadan çağırırsan konuşmayı tarar, skill'e dönüşmeye değer en
  fazla üç şey önerir ve hangisini istediğini sorar.
- **Yazmadan önce sorar.** Her seferinde, tek mesajda:

  | Soru | Seçenekler |
  |---|---|
  | Ad | boşta olan iki üç öneri |
  | Model gücü | `light` (işi betik yapar, en ucuzu), `standard` (oturumun modeli adımları izler), `strong` (planlar, kendi sonucunu denetler, başka ajanlar kullanabilir) |
  | Genişlik | `small` (tek `SKILL.md`), `medium` (yanında bir betik ya da başvuru dosyası), `large` (komutları olan bir yardımcı, başvuru dosyaları, ayarlar) |
  | Nereye | bu sağlayıcı, makinede bulunan bütün sağlayıcılar ya da senin söylediğin bir klasör |

- **Yazdığını denetler.** Ad ve açıklama ajanların ortak sınırları içinde mi, `SKILL.md`'nin
  andığı her dosya yerinde mi, betikler derleniyor mu, doldurulmamış yer kalmış mı, anahtar ya
  da token var mı, bir kişinin ev klasörüne giden yol var mı.
- **Kurar.** Seçtiğin sağlayıcıların skill klasörüne. Zaten kurulu bir skill senin onayın
  olmadan ezilmez; eskisi yedek olarak saklanır.

## Kurulum

```bash
./install.sh new-skill --all
```

## Nasıl çalışır

`SKILL.md` ajana neyi bulacağını, neyi soracağını ve hangi sırayla yapacağını söyler. Yazım
kuralları (bir skill'i dört sağlayıcıda çalıştıran şeyler, her güç ve genişliğin dosya olarak
karşılığı) [references/writing.md](references/writing.md) içindedir ve skill başına bir kez
okunur. Modele bağlı olmaması gereken kısımları yardımcı betik yapar:

```
newskill.py where [--name N]        bulunan sağlayıcılar, skill'leri, adın boşta olup olmadığı
newskill.py draft --name N --description D [--invoke auto]
newskill.py check N|DIR
newskill.py install N|DIR --in P [--also a,b | --all] [--dest DIR] [--replace]
newskill.py drafts · drop N
```

Taslaklar kurulana kadar `~/.local/state/new-skill/drafts/` altında durur. Betik yalnızca
Python 3.8+ ister ve ağa çıkmaz.

## Ne yapmaz

- Bir skill'in çalıştığı modeli değiştiremez: skill, onu çağıran oturumun modelinde çalışır.
  "Model gücü", işin betik, oturumun modeli ve (karşılığını veriyorsa) sağlayıcının CLI'ı
  üzerinden başka bir modele yapılan çağrı arasında nasıl bölüneceğini belirler.
- Skill'i bir yere yayımlamaz. `--dest` ile kendi deponun içine koyabilirsin; gerisi sende.

## Durum

`0.1.0`. Yardımcı betik testlerle kapsanıyor. Akış dört sağlayıcı için yazıldı; soruların ne
kadar iyi sorulduğu her sağlayıcının kendi soru aracına bağlı.

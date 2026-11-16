# Git Sound

Windows aplikacija koja pusta zvuk na push, novu zvjezdicu i fork tvojih GitHub
repozitorija. Radi za javne i privatne repozitorije koji pripadaju prijavljenom
racunu i na kojima imas admin ovlasti. Prijavljeni racun prepoznaje automatski.

## STO POKRENUTI

**PRVI PUT: DVOKLIK NA `INSTALL.bat`, ZATIM NA `START_BACKGROUND.bat`.**

**SVAKI SLJEDECI PUT: DVOKLIK NA `START_BACKGROUND.bat`.**

**ZA ZAUSTAVLJANJE: DVOKLIK NA `STOP.bat`.**

`START.bat` je alternativa s vidljivim prozorom. Odaberi jedan nacin pokretanja.
`TEST_PUSH.bat` i `TEST_STAR.bat` samo testiraju zvuk, ne pokrecu pracenje.
Datoteke `.py` i `.ps1` koriste se interno; pokretanje obavljaju `.bat` datoteke.

## Prvo pokretanje

1. Instaliraj Python 3.10+ i Git for Windows s Git Credential Managerom.
2. Prijavi Git u GitHub preko Git Credential Managera ili postavi GITHUB_TOKEN
   kao varijablu okruzenja. Token nemoj upisivati u datoteke projekta.
3. Pokreni INSTALL.bat. Izradit ce lokalni config.json, provjeriti prijavu i
   preuzeti cloudflared sa SHA256 provjerom ako jos nije instaliran.
4. Pokreni START_BACKGROUND.bat za rad u pozadini ili START.bat za prozor sa zapisom.

Za fine-grained token odaberi svoj racun, All repositories, Webhooks: Read and
write te Metadata: Read. Organizacijski i tudji repozitoriji nisu automatski
ukljuceni. Webhookovi se postavljaju automatski; ne popunjavaj Add webhook rucno.
Novi repozitoriji dodaju se unutar 15 minuta dok aplikacija radi.

## Pjesme bez uredjivanja konfiguracije

U mapu sounds stavi WAV ili MP3 datoteku s odgovarajucim prefiksom:

- push_ime.wav ili push_ime.mp3
- star_ime.wav ili star_ime.mp3
- fork_ime.wav ili fork_ime.mp3

Umjesto ime moze stajati bilo koje ime pjesme. Velika i mala slova nisu vazna.
Promjena imena ili zamjena datoteke vrijedi vec pri sljedecem dogadjaju,
bez ponovnog pokretanja. U config.json ostavi sounds postavke na auto.

Ako imas vise pjesama za isti dogadjaj, svira najnovije izmijenjena; pri istom
vremenu izmjene odluka se donosi po imenu. Za jednoznacan odabir ostavi jednu.
Ako nema nijedne odgovarajuce datoteke, koristi ugradjenu generiranu melodiju.
Obicni push.wav bez podvlake ne smatra se prilagodjenom pjesmom.
Reprodukcija traje najvise 15 sekundi. Kraci zvuk zavrsava ranije.
Preimenovanje MP3 datoteke u WAV ne pretvara stvarni audio format.

TEST_PUSH.bat testira push, TEST_STAR.bat testira star, a naredba
python git_sound.py --test fork testira fork. STOP.bat gasi aplikaciju i tunel.
Za promjenu racuna ili porta potrebno je ponovno pokretanje.

## Rad i ogranicenja

Racunalo mora biti budno i povezano na internet. Automatsko pokretanje s
Windowsima nije ukljuceno. Koristi Cloudflare Quick Tunnel bez jamstva
raspolozivosti. Pri ponovnom pokretanju aplikacija azurira webhook adrese.
Cloudflare prenosi webhook sadrzaj, ukljucujuci metapodatke privatnih dogadjaja.
Prekid tunela pokusava se popraviti nakon 60 sekundi.

Za vrijeme prekida neki dogadjaji mogu izostati. Neuspjelu dostavu po potrebi
ponovi kroz GitHub Settings > Webhooks > Recent Deliveries > Redeliver.
Zvukovi se pustaju redom, s najvise 30 na cekanju. Pun red vraca HTTP 503.
Dostava se pamti prije reprodukcije; kvar zvuka ili nasilno gasenje mogu je preskociti.
Uklanjanje zvjezdice ne pusta zvuk. Push svira jednom po pushu, ne po commitu.

## Git i privatni podaci

config.example.json je javni predlozak bez vezanog korisnickog racuna.
config.json je tvoja lokalna konfiguracija. Prazni owners znaci automatski racun.
Tvoje pjesme, tajni kljuc, logovi, konfiguracija, baza dostava i popisi privatnih
repozitorija iskljuceni su iz Gita. Dijele se samo kod i tri generirane melodije.
Ne brisi webhook_registry.json: cuva ID-jeve webhookova ove instalacije.
Status je u webhook_status.json, a greske i imena odabranih zvukova u git_sound.log.

Zaustavljanje aplikacije ne brise webhookove na GitHubu. Za potpuno uklanjanje
izbrisi njezine webhookove kroz Settings > Webhooks svakog repozitorija.
ID-jeve pronadji u lokalnom webhook_registry.json.

Projekt i generirane melodije su dostupni pod MIT licencom. Dodatne tehnicke
upute su u README.md. Trenutno su podrzani Windows 10 i Windows 11.

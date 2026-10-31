"""Catalogue d'ingrédients de départ, rédigé pour le projet (source de `seed_ingredients`).

Format d'une ligne : nom | rayon | allergènes | drapeaux | alias | densité (g/ml)
Rayons : F fruits et légumes, B boucherie-poissonnerie, D crèmerie, K boulangerie, S épicerie
salée, W épicerie sucrée, C condiments et épices, Z surgelés, R boissons, M divers.
Allergènes : gl gluten, cr crustacés, eg œufs, fi poissons, pe arachides, so soja, mi lait,
tn fruits à coque, ce céleri, mu moutarde, se sésame, su sulfites, lu lupin, mo mollusques.
Drapeaux : s produit de base (placard), u allergènes non confirmés (composition variable).
"""

AISLES = {
    "F": "fruits_vegetables",
    "B": "butcher_fish",
    "D": "dairy",
    "K": "bakery",
    "S": "savory_grocery",
    "W": "sweet_grocery",
    "C": "condiments_spices",
    "Z": "frozen",
    "R": "drinks",
    "M": "misc",
}
ALLERGENS = {
    "gl": "gluten",
    "cr": "crustaceans",
    "eg": "eggs",
    "fi": "fish",
    "pe": "peanuts",
    "so": "soy",
    "mi": "milk",
    "tn": "tree_nuts",
    "ce": "celery",
    "mu": "mustard",
    "se": "sesame",
    "su": "sulphites",
    "lu": "lupin",
    "mo": "molluscs",
}

CATALOG = """
oignon|F|||oignons;oignon jaune
oignon rouge|F
oignon nouveau|F|||ciboule;oignons nouveaux
échalote|F
ail|F|||gousse d'ail;gousses d'ail;ail frais
carotte|F
pomme de terre|F|||patate;pommes de terre
patate douce|F
courgette|F
aubergine|F
poivron|F|||poivron rouge;poivron vert;poivron jaune
tomate|F|||tomates
tomate cerise|F
concombre|F
salade|F|||laitue;salade verte;mâche
roquette|F
épinards|F|||épinard;jeunes pousses d'épinards
champignon|F|||champignons de Paris;champignon de Paris;champignons
poireau|F
chou-fleur|F|||chou fleur
brocoli|F
chou|F|||chou vert;chou blanc
chou rouge|F
haricots verts|F|||haricot vert
petits pois|F|||petit pois
courge|F|||butternut;potiron;potimarron;citrouille
navet|F
radis|F
betterave|F|||betterave cuite
fenouil|F
céleri-rave|F|ce||céleri rave
céleri branche|F|ce||branche de céleri;céleri
asperge|F|||asperges
artichaut|F
maïs|F|||épi de maïs
citron|F|||citrons;jus de citron
citron vert|F|||lime
orange|F|||oranges;jus d'orange
pomme|F|||pommes
poire|F|||poires
banane|F|||bananes
fraise|F|||fraises
framboise|F|||framboises
myrtille|F|||myrtilles
mangue|F
ananas|F
pêche|F|||pêches;nectarine
abricot|F|||abricots
raisin|F
melon|F
avocat|F|||avocats
gingembre|F|||gingembre frais
persil|F|||persil plat;persil frisé
bouquet garni|F
coriandre|F|||coriandre fraîche
basilic|F|||basilic frais
ciboulette|F
menthe|F|||menthe fraîche
thym|F|||thym frais;thym séché;thym sec
romarin|F|||romarin frais
laurier|F|||feuille de laurier;feuilles de laurier
aneth|F
estragon|F
sauge|F
poulet|B|||blanc de poulet;filet de poulet;filets de poulet;escalope de poulet;cuisse de poulet;cuisses de poulet;haut de cuisse de poulet;poulet entier
dinde|B|||escalope de dinde;filet de dinde
bœuf|B|||boeuf;rôti de bœuf;bœuf à braiser;paleron;bavette;steak
bœuf haché|B|||boeuf haché;viande hachée;steak haché;viande de bœuf hachée
veau|B|||escalope de veau;rôti de veau
porc|B|||filet mignon;filet mignon de porc;côte de porc;côtes de porc;rôti de porc;échine
lardons|B|||lardon;poitrine fumée
jambon|B||u|jambon blanc;jambon cuit
jambon cru|B||u|
saucisse|B||u|saucisses;saucisse de Toulouse;saucisse de Strasbourg
chorizo|B||u
merguez|B||u
canard|B|||magret de canard;cuisse de canard
agneau|B|||gigot d'agneau;épaule d'agneau;souris d'agneau
saumon|B|fi||pavé de saumon;pavés de saumon;filet de saumon;saumon frais
cabillaud|B|fi||dos de cabillaud;filet de cabillaud;colin;lieu noir;poisson blanc;filet de poisson blanc
thon|B|fi||thon en boîte;thon au naturel;thon à l'huile;steak de thon
sardines|B|fi||sardine;sardines en boîte
truite|B|fi
anchois|B|fi||filets d'anchois
crevettes|B|cr||crevette;crevettes décortiquées
moules|B|mo||moule
calamars|B|mo||calamar;encornets
lait|D|mi||lait demi-écrémé;lait entier;lait écrémé|1.03
crème fraîche|D|mi||crème fraiche;crème épaisse;crème fraîche épaisse
crème liquide|D|mi||crème fleurette;crème entière;crème
beurre|D|mi||beurre doux;beurre demi-sel;beurre fondu;noix de beurre|0.91
yaourt nature|D|mi||yaourt;yaourts;yaourt grec;yogourt
fromage blanc|D|mi||faisselle
fromage râpé|D|mi||emmental râpé;gruyère râpé;gruyère;emmental;comté;fromage
parmesan|D|mi||parmigiano
mozzarella|D|mi
fromage de chèvre|D|mi||chèvre;chèvres;bûche de chèvre;chèvres bûche;chèvre bûche;chèvre frais
feta|D|mi
ricotta|D|mi
mascarpone|D|mi
camembert|D|mi||brie;reblochon
fromage frais|D|mi||saint-môret;st môret;boursin;fromage à tartiner;philadelphia
œuf|D|eg||oeuf;œufs;oeufs;oeufs entiers;jaune d'œuf;jaunes d'œufs;blanc d'œuf;blancs d'œufs
mayonnaise|C|eg,mu
lait de coco|S|||crème de coco;lait de coco en boîte
lait d'amande|D|tn||boisson amande
boisson soja|D|so||lait de soja
pain|K|gl||baguette;pain de campagne;pain complet;tranche de pain
pain de mie|K|gl,mi,so||tranches de pain de mie;pain de mie complet
wrap|K|gl||tortilla;tortillas;galette de blé;wraps
pain à burger|K|gl,mi,eg,se||pains à burger;buns
brioche|K|gl,mi,eg||pain brioché
pâte brisée|K|gl,mi||pâte à tarte;pâte sablée
pâte feuilletée|K|gl,mi
pâte à pizza|K|gl
chapelure|S|gl||panure
pâtes|S|gl||spaghetti;tagliatelles;macaronis;penne;coquillettes;fusilli;torsades;farfalle;linguine;lasagnes;feuilles de lasagne;vermicelles
riz|S|||riz basmati;riz long;riz rond;riz complet;riz thaï;riz à risotto;riz arborio
semoule|S|gl||semoule de blé;couscous;semoule fine;semoule de couscous
boulgour|S|gl
quinoa|S
lentilles|S|||lentille;lentilles vertes;lentilles corail;lentilles blondes
pois chiches|S|||pois chiche
haricots rouges|S|||haricot rouge;haricots blancs;haricot blanc;flageolets;haricots secs
tomates concassées|S|||tomate concassée;tomates pelées;boîte de tomates;tomates en boîte;coulis de tomate;purée de tomates;passata
concentré de tomate|S|||double concentré de tomate
sauce tomate|S|||sauce tomate cuisinée
olives|S|||olive;olives noires;olives vertes
câpres|S|su
cornichons|S|su,mu||cornichon
bouillon de légumes|S|ce||cube de bouillon de légumes;bouillon cube de légumes;bouillon légumes
bouillon de volaille|S|ce||cube de bouillon de volaille;fond de volaille;bouillon de poule
bouillon de bœuf|S|ce||cube de bouillon de bœuf;fond de veau;fond de bœuf;bouillon de boeuf
bouillon|S|ce||cube de bouillon;bouillon cube
maïs en boîte|S|||maïs doux
farine|S|gl|s|farine de blé;farine T55;farine tamisée|0.55
fécule de maïs|S|||maïzena;fécule;fécule de pomme de terre
levure chimique|S|gl||levure;sachet de levure
sucre|W||s|sucre en poudre;sucre semoule;sucre cristallisé|0.85
sucre roux|W|||cassonade;sucre complet
sucre glace|W
sucre vanillé|W|||vanille;extrait de vanille;gousse de vanille;sucre vanille
miel|W|||miel liquide|1.4
sirop d'érable|W
chocolat noir|W|so||chocolat pâtissier;chocolat à cuire;tablette de chocolat
chocolat au lait|W|mi,so
pépites de chocolat|W|mi,so
cacao|W|||cacao en poudre;cacao maigre
confiture|W|||confiture de fraises;confiture d'abricots
pâte à tartiner|W|tn,mi,so||nutella
flocons d'avoine|W|gl||avoine
muesli|W|gl,tn,so||céréales
biscuits|W|gl,mi,eg,so|u|biscuit;boudoirs;spéculoos;petits-beurre;biscuits secs;palets bretons
compote|W|||compote de pommes
amandes|W|tn||amande;amandes effilées;amandes en poudre;poudre d'amande;poudre d'amandes
noisettes|W|tn||noisette;noisettes concassées;poudre de noisette
noix|W|tn||noix de Grenoble;cerneaux de noix
noix de cajou|W|tn
pistaches|W|tn||pistache
pignons de pin|W|tn||pignons
cacahuètes|W|pe||cacahuète;arachides;cacahuètes salées
beurre de cacahuète|W|pe||beurre de cacahuètes
pruneaux|W||u|pruneau;pruneaux d'Agen;pruneaux dénoyautés
raisins secs|W|su||raisin sec;raisins de Corinthe
abricots secs|W|su||abricot sec
noix de coco râpée|W|||noix de coco;coco râpée
sel|C||s|sel fin;gros sel;fleur de sel;sel de mer
poivre|C||s|poivre noir;poivre du moulin;poivre moulu;poivre blanc;poivre en grains
huile d'olive|C||s|huile d'olive vierge extra;huile olive|0.92
huile de tournesol|C||s|huile;huile végétale;huile de colza;huile d'arachide;huile neutre|0.92
huile de sésame|C|se
vinaigre balsamique|C|su|s|vinaigre balsamique blanc;crème de balsamique
vinaigre de vin|C|su|s|vinaigre;vinaigre blanc;vinaigre de cidre;vinaigre de riz
moutarde|C|mu||moutarde de Dijon;moutarde forte;moutarde à l'ancienne
ketchup|C
sauce soja|C|so,gl||sauce soja salée;sauce soja sucrée;tamari
sauce worcestershire|C|fi||worcestershire
nuoc-mam|C|fi||sauce poisson;nuoc mam
tabasco|C|||sauce piquante
harissa|C
curry|C|ce,mu||poudre de curry;curry en poudre
curcuma|C
paprika|C|||paprika doux;paprika fumé;piment doux
cumin|C|||cumin moulu;graines de cumin
coriandre moulue|C
cannelle|C|||cannelle moulue;bâton de cannelle
muscade|C|||noix de muscade
piment|C|||piment de Cayenne;piment d'Espelette;piment en poudre;piment oiseau;flocons de piment
herbes de Provence|C|||origan;herbes aromatiques;herbes séchées;persil séché
gingembre moulu|C
ras el hanout|C|||épices marocaines;mélange d'épices
quatre-épices|C|||quatre épices;épices
safran|C
cardamome|C
clou de girofle|C|||clous de girofle;girofle
ail en poudre|C|||oignon en poudre;ail semoule
pesto|C|tn,mi||pesto vert;pesto rouge;sauce pesto
tahini|C|se||purée de sésame
graines de sésame|C|se||sésame
graines de courge|C|||graines de tournesol;graines
petits pois surgelés|Z|||petits pois en surgelé
épinards surgelés|Z|||épinards hachés surgelés
légumes surgelés|Z|||poêlée de légumes;mélange de légumes;légumes pour wok;macédoine de légumes;légumes pour couscous
haricots verts surgelés|Z
frites surgelées|Z|||frites
glace vanille|Z|mi,eg||glace;crème glacée
eau|M||s|eau froide;eau chaude;eau tiède;eau bouillante;eau de cuisson
vin blanc|R|su||vin blanc sec
vin rouge|R|su
bière|R|gl,su
jus de pomme|R
thé|R|||thé noir;thé vert;infusion
café|R|||café fort;expresso
""".strip()

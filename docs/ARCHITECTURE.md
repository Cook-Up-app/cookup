# Architecture

Un projet Django unique, déployé comme une fonction Vercel (`config/wsgi.py`), PostgreSQL Supabase via le pooler transactionnel. Voir `SPEC.md` sections 3 à 5.

## Allergies, placard et styles

- `core/lexicon.py` : synonymes d'allergènes et familles d'aliments (données seules). `households/restrictions.py` : reconnaissance d'un texte (allergène > famille > catalogue > libre) et exclusion réelle (`Coverage` : allergènes déclarés + jeux de mots). `DinerRestriction.food_group` s'ajoute à `allergen` et `ingredient_name`.
- Moteur : une restriction stricte alimente `strict_allergens` et `strict_word_sets` (règle dure) ; une restriction « intolérance/à éviter » abaisse le goût des ingrédients du catalogue concernés (auparavant ignorée pour le texte libre).
- Placard : `PantryBulkForm` (un champ par rayon, une seule requête), `shopping.services.stock_always` (`ignore_conflicts`, l'existant reste intact).
- Styles : `HouseholdSettings.liked_cuisines/avoided_cuisines/spice_tolerance/exoticism` ; `catalog/cuisine.py` déduit cuisine et piment ; critère `planner/engine/style.py` (poids 10, ne filtre jamais).
- Limite connue : la déduction de cuisine est heuristique (mots-clés) ; une étiquette `cuisine:xxx` sur la recette prime.

## Inscription libre

- `apps/accounts/adapters.SignupAdapter.is_open_for_signup` lit `SIGNUP_OPEN` ; `apps/accounts/forms.SignupForm` ajoute le prénom au formulaire d'allauth. Le foyer est créé à la première visite par `households.services.ensure_household` (une seule voie, comme avant).
- Isolation : tout reste filtré par `for_household` ; un inscrit n'a qu'une adhésion, la sienne. L'invitation reste le seul moyen de rejoindre un foyer existant.
- `mfa_required` (middleware) : staff ou superuser uniquement.
- Limitation de débit : `ACCOUNT_RATE_LIMITS["signup"] = 5/h/ip` dans `DatabaseCache` ; en production `ALLAUTH_TRUSTED_CLIENT_IP_HEADER = x-vercel-forwarded-for` (sans cela, tous les visiteurs partageraient une IP). Réponse 429 en français (`handler429`).
- Limites connues : pas de vérification d'e-mail ni de réinitialisation autonome (aucun service d'e-mail).

## État après la refonte front-end

- **Design system** : `tokens.css` (couleurs, espacements, contrastes AA vérifiés par test), `base.css`, `layout.css` (coque), `components.css`, `print.css`. Aucun style ni script en ligne (CSP stricte). Icônes : sprite SVG (`components/icons.html`, balise `{% icon %}`).
- **Coque** : `_document.html` → `base.html` (application) / `base_auth.html` (cartes centrées) ; gabarits allauth surchargés. La navigation vient du processeur de contexte `apps.core.context.ui`.
- **Formulaires** : `FORM_RENDERER=TemplatesSetting`, surcharges dans `templates/django/forms/` (pastilles pour cases et radios).
- **Assistant d'accueil** (`apps/onboarding`) : registre d'étapes (`@step`), une question par écran, enregistrement immédiat, passer/retour/quitter. Redirection seulement pour un foyer neuf (`HouseholdSettings.onboarded_at`).
- **Accueil** : `apps/planner/dashboard.py` (menu du jour, demain, courses).
- **Hors ligne** : le JavaScript de M6 est inchangé, relié par des attributs `data-*`.
- **Dev** : `seed_demo` et `/dev/connexion/<profil>` (`DEV_LOGIN`, vrai seulement en local).
- Écarts : pas de HTMX ; service worker non testé dans le navigateur intégré.

## État après M0

- `config/settings/{base,local,production}.py` : réglages communs, développement, production (HSTS, cookies `__Host-`, SSL redirect, WhiteNoise manifest).
- `apps/core` : `/sante` (état + base), `/internal/cron/daily` (Bearer `CRON_SECRET`, comparaison en temps constant, maintien de la base active), page d'accueil provisoire, middleware `Permissions-Policy`, lecture typée de l'environnement.
- Sécurité : CSP native Django 6.1 (`SECURE_CSP`, sans `unsafe-inline`/`unsafe-eval`), `X-Frame-Options`, `Referrer-Policy`, `nosniff`.
- `vercel.json` : région `cdg1`, `maxDuration` 60 s (Hobby : 300 s max, vérifié), cron quotidien 05:00.

## État après M6

- **PWA** : `/manifest.webmanifest`, icônes (script `scripts/make_icons.py`), et un service worker servi à la racine par une vue Django (`/sw.js`, `Service-Worker-Allowed: /`, sans cache) : un fichier sous `/static/` aurait une portée limitée à `/static/`, et le dossier statique n'est de toute façon pas dans la fonction Vercel. Les caches portent la version du déploiement (`VERCEL_GIT_COMMIT_SHA`).
- **Stratégies de cache** : enveloppe de l'application en cache d'abord ; pages de données (courses, menus, recettes ouvertes) réseau d'abord avec repli sur le cache ; jamais en cache les POST, la connexion, le compte, l'administration et les routes internes.
- **Synchronisation des courses** : cocher envoie « mettre à l'état X » (idempotent) et non « inverser » ; chaque geste est horodaté côté client, enregistré dans IndexedDB (file d'attente), appliqué tout de suite à l'écran, puis rejoué par lot vers `/courses/<menu>/synchroniser`. Le serveur applique ligne par ligne selon l'heure du geste (**le dernier gagne**, horloge bornée à +5 min), répond par un statut par opération et l'état de la liste. Déclencheurs du rejeu : retour du réseau, ouverture de la page, retour au premier plan, Background Sync quand il existe, essais espacés (2 s, 4 s… 5 min). Les ajouts hors ligne utilisent un identifiant créé côté client (pas de doublon au rejeu).
- **Déconnexion** : en ligne, la file est d'abord synchronisée, puis caches et IndexedDB sont vidés. Hors ligne, les données locales sont effacées et la fermeture de la session serveur est faite au retour du réseau (limite : la session reste valide jusque-là).
- **Mode cuisine** (`/recettes/<id>/cuisine`) : étapes en grand texte une à une, minuteurs proposés depuis les durées de l'étape, écran maintenu allumé (Wake Lock) ; sans JavaScript, simple liste lisible.
- **Export** : texte copié, partage système, impression (feuille de style dédiée), construits depuis la page donc disponibles hors ligne.
- **Apprentissage des goûts** : les notes du foyer deviennent des goûts d'ingrédients (écart à la note habituelle, lissé et borné de -2 à +2) pour les convives sans goût saisi ; un goût saisi à la main prime toujours. Favoris et exclusions restent des critères directs.
- **Exploitation** : tâche quotidienne vérifiable via `/sante` (`keepalive`), purge des invitations et sessions expirées, sauvegarde hebdomadaire chiffrée (`docs/operations.md`).
- **Vérifié en navigateur réel** (serveur local, base de test) : cases cochées appliquées à l'écran puis synchronisées, coupure du serveur avec deux cases cochées (2 opérations en file), retour du serveur et rejeu automatique (file vide, état serveur correct) ; mode cuisine (étapes, minuteur « 1 h 15 »). Ce test a révélé et fait corriger un défaut : la synchronisation attendait `serviceWorker.ready` et ne partait jamais si le service worker était indisponible.
- **Non vérifié** : le service worker lui-même (le panneau navigateur utilisé refuse l'enregistrement : la requête `/sw.js` n'est jamais émise). Sa logique est testée sous node avec des simulations de `caches` et `fetch` (13 cas) ; l'installation réelle, le hors ligne complet et iOS restent à essayer sur un appareil.
- **Écarts** : pas d'HTMX ; JavaScript total d'environ 24 Ko avant compression (budget 50 Ko) ; Background Sync absent d'iOS/Safari (les autres déclencheurs prennent le relais).

## État après M5

- **Mode Cookeo** : un créneau est « Cookeo » ou « Classique » (mode mixte : part exacte tirée de façon reproductible) ; une recette Cookeo exige l'équipement du foyer et ne peut remplir qu'un créneau Cookeo, et réciproquement. Un seul plat principal par créneau, donc une seule préparation Cookeo à la fois.
- **Capacité** : cuve de 6 L = 6 portions (restes compris). Au-delà, le formulaire avertit et propose de **scinder la cuisson** ; avec l'option, l'explication du repas indique « à cuire en N fois ».
- **Équipement obligatoire** : les modes Cookeo et mixte sont refusés sans l'équipement, dans le formulaire de menu, les réglages et le service (`CookeoUnavailable`) ; le formulaire propose Classique si l'équipement a disparu.
- **Fiche recette** : bandeau avec programme, minutes sous pression et usage du couvercle Extra Crisp (`cookeo_program`) ; « programme non précisé par la source » pour une recette importée.
- **moulinex.fr** : adaptateur par sitemap, contenu minimal, désactivé par défaut (voir `docs/sources.md`). La récupération sait désormais ne lire que le début d'un document volumineux.
- **Écarts** : pas d'envoi vers l'appareil (jamais prévu) ; le « mode mixte » s'ajuste avec un curseur de 0 à 100 %.

## État après M4

- **Calcul** (`apps/shopping/aggregation.py`, fonctions pures) : mise à l'échelle des portions réellement cuisinées (restes compris, comptés une seule fois), somme par ingrédient canonique et unité de base (g, ml, pièce), fusion masse/volume par la densité quand elle est connue (sinon deux lignes), retrait du placard, arrondi à une quantité achetable (pièces entières, 50 g pour la viande, 10 g ou 10 ml sinon, nombre de conditionnements), ingrédients facultatifs signalés, recettes d'origine conservées. Les cas chiffrés de la spec (60 ml d'huile, 1,5 oignon arrondi à 2) sont des tests.
- **Régénération sans perte** (`services.sync_list`) : chaque ligne calculée a une clé stable (`ing:<id>:<unité>` ou texte replié) ; au recalcul, les lignes restantes gardent leur case cochée, les lignes disparues sont retirées, les lignes retirées à la main restent masquées, les lignes manuelles ne sont jamais touchées. La liste se remet d'elle-même à jour quand l'empreinte du menu change.
- **Placard** (`PantryItem`) : les produits de base du catalogue sont réputés en stock ; le foyer peut en racheter (« toujours en stock » décoché) ou déduire une quantité.
- **Rayons** : ordre par défaut d'un parcours de magasin, réordonnable et mémorisé par foyer (`HouseholdSettings.aisle_order`).
- **Écarts** : cases à cocher en formulaires avec rechargement (pas de HTMX) ; hors ligne, export et partage relèvent de M6.

## État après M3

- **Moteur** (`apps/planner/engine/`, Python pur, sans Django) : `rules` (contraintes dures, une fonction par règle, registre `RULES`), `criteria` (7 critères de score enregistrés : goûts 30, notes 15, fraîcheur 20, diversité 15, anti-gaspillage 10, budget 5, saison 5), `selection` (créneaux les plus contraints d'abord, tirage softmax reproductible par graine, 200 essais d'amélioration), `planning` (mode Cookeo/mixte par créneau, jours « restes »), `failure` (rapport chiffré des contraintes qui bloquent).
- **Sécurité alimentaire** : allergie stricte = exclusion totale ; **toute recette dont un ingrédient est inconnu, à vérifier ou aux allergènes non confirmés est écartée dès qu'une allergie ou un régime existe** (échec côté sûr). Les intolérances et aliments à éviter baissent le score sans exclure.
- **Frontière** (`loading`, `services`) : une requête par table pour charger le catalogue, conversion en objets du moteur ; le remplacement d'un repas est **revalidé** par les règles dures avant d'être appliqué.
- **Données** : `MenuPlan` (paramètres figés, graine), `MenuSlot` (verrouillé, hors maison, restes, explication), `HouseholdSettings`, `TastePreference` ; `Ingredient.diet_flags` et `protein` dérivés par `catalog.traits`.
- **Écarts** : formulaires classiques avec redirection, sans HTMX (aucune bibliothèque téléchargée) ; pas encore de déplacement/duplication d'un repas ; invités ponctuels au niveau du menu, pas du repas.

## État après M2

- **Catalogue** (`apps/catalog`, partagé entre foyers) : `Ingredient` (nom canonique, rayon, allergènes, `allergens_reviewed`), `Recipe` (empreinte unique, `search_text` replié sans accents + `search_vector` français, index GIN et trigrammes), `RecipeIngredient` (texte brut toujours conservé), `RecipeEquipment`, `RecipeFeedback` (par foyer). Les ingrédients et recettes de départ se chargent par `make seed` (`seed_catalog`, idempotent).
- **Normalisation** (`text`, `normalization`, `matching`, fonctions pures) : quantité, unité (table unique `core.units`), nom ; rattachement exact, puis par inclusion (marqué « à vérifier » si un mot inconnu reste), puis similarité `pg_trgm`. Rien n'est deviné : l'inconnu garde son texte brut et un drapeau.
- **Sources** (`apps/sources`) : contrats `Searchable`/`Fetchable`/`Parsable`, registre, `PoliteFetcher` (liste blanche, SSRF avec contrôle de l'adresse réellement jointe, robots.txt avec jokers, débit en base, taille et durée plafonnées, redirections revalidées), `UrlImportSource`, `MarmitonSource`, file `ImportJob`, tâche hebdomadaire.
- **Écarts** : pas d'extension `unaccent` (repliement fait en Python, de façon identique à l'index et à la requête) ; pas de `loaddata` mais une commande de chargement.

## État après M1

- **Authentification** : `accounts.User` (UUID, e-mail unique insensible à la casse), Argon2id, allauth (sessions, TOTP, passkeys, codes de récupération, réauthentification). Inscription fermée (`ClosedAccountAdapter`).
- **Refus par défaut** : `AccessPolicyMiddleware` (dernier de la pile, ses redirections traversent CSP et en-têtes) exige une session sur toute route absente de `PUBLIC_URL_NAMES`. La MFA enrôlée (TOTP ou passkey ; les codes de récupération seuls ne comptent pas) n'est exigée que des administrateurs (`mfa_required` : staff ou propriétaire de foyer) ; un simple membre qui l'active se la voit demander à la connexion.
- **Foyer automatique** : `ensure_household` crée « Mon foyer » (4 portions) au premier passage ; les invitations sont facultatives et n'expirent pas par défaut. Sessions d'un an, prolongées à chaque requête.
- **Foyers** (`apps/households`) : `Household`, `Membership` (propriétaire/membre), `Invitation` (jeton haché, 7 jours, usage unique), `Diner`, `DinerRestriction`, `Equipment`, `HouseholdEquipment`. Tout accès privé passe par `objects.for_household(...)` (`core.querysets`). Les vues utilisent `household_required` / `owner_required` ; une ressource d'un autre foyer répond 404.
- **Sans e-mail** : le propriétaire génère les liens d'invitation et de réinitialisation (`/foyer/`), affichés une seule fois ; la réinitialisation exige une réauthentification récente, comme le retrait d'un membre.
- **Limitation de débit** : compteurs allauth dans `DatabaseCache` (table `django_cache`, créée par `core.0001`), partagés entre instances serverless.
- **RLS** : `post_migrate` (`core.apps`) active Row Level Security sans politique sur toutes les tables du schéma `public`, y compris celles des jalons suivants.
- **Administration** : montée sous `ADMIN_PATH` seulement (vide en production), connexion via allauth donc MFA incluse.

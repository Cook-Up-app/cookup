# Sources de recettes : vérification préalable (SPEC section 14)

> **Décision du propriétaire (2026-10-31)** : conditions d'utilisation de Marmiton lues, aucune restriction pour ce projet ; seuls les `robots.txt` font foi. Import le plus automatisé possible dans leurs limites, une fois par semaine. Les constats ci-dessous restent la base technique ; la section « Mise en œuvre M2 » en fin de document décrit ce qui a été construit.

Vérification du 2026-10-31, avec le `User-Agent` `CookupRecipeCheck/0.1 (… contact: millotflorentin@gmail.com)`, 2 s entre requêtes, une seule page de recette par site. Ce n'est pas un avis juridique.

## marmiton.org

| Point | Constat |
| --- | --- |
| `robots.txt` | Accessible. Pages de recettes (`/recettes/recette_*.aspx`) **autorisées**. La recherche simple `/recettes/recherche.aspx?aqt=<mots>` n'est pas interdite, mais `?type=*`, `aqt=*page*`, `aqt=*start*`, `/dossiers/recherche.aspx*`, `/recettes/recette-impression_*` et `/mon-espace/*` le sont. Aucune directive `Crawl-delay`. |
| Conditions d'utilisation | **Non lues** : le pied de page est rendu par JavaScript, les chemins usuels (`/cgu`, `/mentions-legales`…) répondent 404 et la recherche web ne renvoie que des sites homonymes. À consulter par le propriétaire sur le site. |
| JSON-LD | Oui : bloc `schema.org/Recipe` avec `name`, `recipeIngredient` (texte français, ex. « 300 g de farine »), `recipeInstructions`, `recipeYield`, `prepTime`, `cookTime`, `totalTime`, `recipeCategory`, `keywords`, `suitableForDiet`, `nutrition`, `aggregateRating`. |
| `recipe-scrapers` | Prend en charge `marmiton.org` (version 15.12.0 résolue avec le plafond de dates du projet). |
| Anti-robots | Aucun CAPTCHA ni blocage rencontré sur 3 requêtes. |

**Décision proposée** : Classique A (import par URL collée) actif. Classique B (recherche automatique) : adaptateur écrit mais **désactivé** (`SOURCE_MARMITON_ENABLED=false`) tant que les conditions d'utilisation n'ont pas été lues par le propriétaire ; à exclure si elles interdisent l'extraction automatisée.

## moulinex.fr (Groupe SEB)

| Point | Constat |
| --- | --- |
| `robots.txt` | Pages `/recipe/detail/…` **non interdites**. Interdits : `/search?*`, toute URL avec `?query=`, `?q=`, `?text=`, `?filters`, etc. (donc **pas de recherche automatique** possible), et le robot `MJ12bot`. |
| Conditions d'utilisation | Lues (<https://legal.groupeseb.com/Core/FR/fr/DU.html>). Elles interdisent « toute reproduction, représentation, adaptation, […] réutilisation totale ou partielle du Site et/ou des Contenus, par tout procédé, et sur tout support » et de copier tout ou partie du site. **Conflit probable avec le stockage du contenu des recettes**, même pour un usage privé. |
| JSON-LD | Oui sur l'exemple de la spec : `schema.org/Recipe` avec ingrédients, étapes, portions, durée totale. Pas de `prepTime` ni `cookTime`. L'exemple est en **néerlandais** ; les pages françaises n'ont pas été échantillonnées. Aucun `cookeo_program` structuré. |
| `recipe-scrapers` | Prend en charge `moulinex.fr`. |
| Anti-robots | Aucun blocage rencontré sur 2 requêtes. |

**Décision proposée (à confirmer en M5)** : ne pas écrire d'adaptateur `moulinex` en M2. Le mode Cookeo repose d'abord sur les recettes originales du jeu de départ et la saisie manuelle. Si le propriétaire veut tout de même l'import, le limiter à une action manuelle qui ne stocke que les ingrédients, durées et portions avec le lien d'origine, sans les étapes ni les images.

## Garde-fous communs
`User-Agent` honnête avec contact, 1 requête par seconde maximum, respect de `robots.txt` et des en-têtes de cache, aucun contournement de protection anti-robots, jamais de scraping pendant la génération d'un menu, un import = une recette = une requête.

## Mise en œuvre M2 (automatisation dans les limites de robots.txt)

- **Découverte** : chaque semaine, 4 recherches thématiques (`apps/sources/themes.py`, rotation sur 60 thèmes dont des recettes Cookeo). Seule la **première page** de `/recettes/recherche.aspx?aqt=<thème>` est demandée : c'est la seule forme que robots.txt autorise (ni `page=`, ni `start=`, ni `type=`).
- **Import** : une recette = une requête, 1 requête par seconde maximum (état partagé en base, donc valable entre invocations serverless), `User-Agent` honnête avec contact, arrêt et pause de 6 h ou du `Retry-After` sur 429/503, aucune requête si robots.txt est injoignable (RFC 9309).
- **Filtre qualité** : les recettes notées sous 3,8 / 5 par la source ne sont pas importées ; les doublons sont détectés par empreinte.
- **Cadence** : cron Vercel le lundi 04:00 (un lot d'environ 40 s) ; workflow GitHub facultatif le lundi 05:00 pour vider la file par lots successifs. Quota : 40 nouvelles recettes par semaine (`SOURCE_IMPORT_WEEKLY_QUOTA`).
- **Activation** : `SOURCE_MARMITON_ENABLED=true` et `SOURCES_CONTACT` renseignés dans Vercel. Désactivable à tout moment.
- **Moulinex** : aucun adaptateur en M2. Les conditions du Groupe SEB (lues plus haut) restent un point d'attention ; décision en M5 avec le propriétaire.

## Mise en œuvre M5 : moulinex.fr (désactivé par défaut)

- **Découverte** : la recherche de moulinex.fr est interdite par robots.txt ; on lit donc le sitemap `Recipe-fr_fr-EUR.xml` (déclaré dans robots.txt, plus de 13 000 recettes). Un seul début de fichier est lu (400 Ko, une requête) et 15 adresses sont tirées au sort chaque semaine, de façon reproductible.
- **Contenu conservé** : ingrédients, durée, portions, lien vers la page d'origine. **Ni étapes ni images**, par prudence vis-à-vis des conditions du Groupe SEB (« toute reproduction, représentation, adaptation, [...] réutilisation totale ou partielle du Site et/ou des Contenus »). Seules les pages françaises sont retenues ; une recette est marquée Cookeo si son titre, ses étiquettes ou ses étapes le mentionnent.
- **Activation explicite** : `SOURCE_MOULINEX_ENABLED=true` ; sans cela le domaine n'est même pas dans la liste autorisée et aucune requête ne part. À activer seulement après décision du propriétaire sur le risque décrit plus haut.

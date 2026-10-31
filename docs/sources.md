# Sources de recettes : vérification préalable (SPEC section 14)

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

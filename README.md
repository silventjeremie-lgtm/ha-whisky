# 🥃 Whisky — Collection pour Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=flat-square)](https://github.com/hacs/integration)

**Whisky** transforme Home Assistant en gestionnaire de collection de whiskies : fiches détaillées (distillerie, fûts, tourbe, embouteillage…), reconnaissance d'étiquette par photo (IA Gemini), statistiques, recherche/filtres et suivi de l'état de chaque bouteille (scellée / ouverte / terminée).

Projet indépendant, dérivé de l'architecture de [Millésime](https://github.com/Redsklns/ha-millesime) (cave à vin) — même style technique (stockage JSON local, carte Lovelace auto-servie), mais vocabulaire et modèle de données entièrement propres au whisky. **Les deux projets sont complètement séparés** : domaine, fichier de données, entités et services différents — aucune donnée de l'un n'est lue ni modifiée par l'autre, et installer Whisky n'a aucun impact sur une installation Millésime existante.

---

## Statut

- [x] Commit 1 — Scaffold du dépôt
- [x] Commit 2 — Modèle de données & stockage
- [x] Commit 3 — Services CRUD
- [x] Commit 4 — Capteurs Home Assistant
- [x] Commit 5 — Reconnaissance photo (Gemini)
- [x] Commit 6 — Formulaire d'ajout/édition
- [x] Commit 7 — Liste & fiche détail
- [x] Commit 8 — Statistiques & filtres
- [x] Commit 9 — Événements pour automatisations
- [x] Commit 10 — Tests
- [x] Commit 11 — Documentation complète
- [x] Commit 12 — Packaging final

**Portée de la v1** (voir aussi Limites connues plus bas) : socle complet — modèle de données, reconnaissance photo, formulaire, liste/détail, statistiques, filtres, entités et services HA. La visualisation 3D et le sommelier IA de Millésime ne sont **pas** repris dans cette v1 (phase 2 éventuelle, non planifiée).

## Avant de pousser ce dépôt sur votre GitHub

Ce projet vous est livré en fichiers locaux : c'est à vous de créer le dépôt GitHub et d'y pousser ce code. Deux champs de `custom_components/whisky/manifest.json` contiennent un nom de dépôt indicatif (`jeremiesilvent/ha-whisky`) à corriger si votre dépôt porte un autre nom :

```json
"documentation": "https://github.com/<vous>/<votre-depot>",
"issue_tracker": "https://github.com/<vous>/<votre-depot>/issues",
```

`codeowners` (`@jeremiesilvent`) peut aussi être ajusté à votre pseudo GitHub réel si différent.

## Installation

### Via HACS (dépôt personnalisé)

Ce dépôt n'est pas (encore) dans la liste par défaut de HACS. Ajoutez-le comme dépôt personnalisé :

1. HACS → menu (⋮) → **Dépôts personnalisés**.
2. URL du dépôt (adaptez à l'endroit où vous avez poussé ce projet), catégorie **Intégration**.
3. Installez **Whisky — Collection**, puis redémarrez Home Assistant.

### Installation manuelle

1. Copiez le dossier `custom_components/whisky` dans `<config Home Assistant>/custom_components/whisky`.
2. Redémarrez Home Assistant.

Dans les deux cas, l'intégration ajoute automatiquement la carte Lovelace (`whisky-card.js`) comme ressource — aucune étape manuelle supplémentaire n'est nécessaire (voir *Limites connues* si l'ajout automatique échoue sur votre installation).

## Configuration

**Paramètres → Appareils et services → Ajouter une intégration → Whisky**.

| Champ | Description |
|---|---|
| Nom de la collection | Libre, par défaut « Whisky ». Titre de l'entrée d'intégration. |
| Clé API Gemini | Optionnelle. Sans clé, l'ajout se fait uniquement à la main (aucun repli automatique sur une base whisky externe — voir *Reconnaissance photo*). Clé gratuite sur [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) ; quota gratuit indicatif : 1 500 requêtes/jour. |

La clé peut être ajoutée ou changée après coup via **Configurer** sur l'intégration (options).

## Ajouter un whisky

Deux façons d'ajouter une fiche depuis la carte (bouton **➕ Ajouter**) :

- **À la main** : formulaire en 9 sections (Identité, Origine, Classification, Caractéristiques, Maturation, Embouteillage, Dégustation, Collection personnelle, Notes & médias — voir *Modèle de données* ci-dessous), plus une section « À l'ajout » (quantité, état initial) visible uniquement à la création.
- **Par photo** (📷 *Identifier par photo*, nécessite une clé Gemini configurée) : prenez ou importez une photo de l'étiquette. L'IA propose des valeurs, **chacune accompagnée d'un niveau de confiance** (Fiable / Moyenne / Faible) ; rien n'est jamais pré-coché à l'aveugle sur un champ déjà rempli à la main, et **rien n'est enregistré tant que vous n'avez pas explicitement validé puis soumis le formulaire**. Voir *Reconnaissance photo* pour le détail des limites.

Ajouter plusieurs exemplaires identiques d'un coup (ex. un lot de 3 bouteilles non encore rangées) se fait via le champ **Quantité** à la création — elles sont ajoutées sans emplacement d'étagère assigné, consultables et modifiables normalement depuis la fiche détail.

## Modèle de données

Une **fiche** = un produit (ex. « Lagavulin 16 Years Old »). Elle regroupe un ou plusieurs **exemplaires physiques** (bouteilles), chacun avec son propre état — vous pouvez ainsi posséder deux bouteilles du même whisky, l'une scellée et l'autre déjà entamée.

| Section | Exemples de champs |
|---|---|
| 🥃 Identité | Nom, **Distillerie**, **Embouteilleur indépendant** (si différent — voir *Reconnaissance photo*), Marque, Expression |
| 🌍 Origine | Pays, Région, Localisation de la distillerie |
| 🏷️ Classification | Type (Single Malt, Blended Malt, Blended Whisky, Single Grain, Bourbon, Rye, Tennessee Whiskey, Corn Whiskey, Irish Single Malt, Irish Pot Still, Japanese Whisky, World Whisky, Other) |
| 🔬 Caractéristiques | Âge, Millésime, Année de mise en bouteille, Degré d'alcool, Volume, Filtré à froid, Couleur naturelle, Tourbé, Niveau de tourbe, PPM |
| 🛢️ Maturation | Type de fût (suggestions libres : Bourbon, First Fill Bourbon, Refill Bourbon, Sherry, Oloroso, PX, Port, Madeira, Wine, Virgin Oak, Mizunara, Multiple Casks…), Numéro de fût, Finition, Durée de maturation |
| 📦 Embouteillage | Lot, Édition, Numéro de bouteille, Nombre total produit, Édition limitée, Mise en bouteille indépendante |
| 👃 Dégustation | Notes générales, Nez, Bouche, Finale |
| 💰 Collection personnelle | Prix d'achat, Valeur actuelle estimée, Devise, Date/lieu d'achat, Emplacement de rangement (texte libre) |
| ⭐ Notes & médias | Note personnelle (/5), Coup de cœur, Commentaires, Photos |
| 🔗 Références externes | Code-barres, identifiant/lien externe, **ID/lien Whiskybase (optionnels, jamais consultés automatiquement)** |

L'état de chaque exemplaire (`bottle_status`) suit le cycle **scellée → ouverte → terminée**, plus un niveau restant (%) suivi manuellement une fois ouverte (voir *Automatisations*). Passer à l'état « terminée » **ne supprime jamais** l'exemplaire : la fiche et son historique restent consultables.

La structure physique (casiers/étagères, plusieurs collections) est disponible via les services `add_rack`/`add_cellar` etc. (repris tels quels de Millésime, déjà agnostiques du contenu) mais la carte v1 ne propose pas encore de sélecteur d'étagère visuel dans le formulaire — voir *Limites connues*.

## Liste, recherche & fiche détail

La carte principale affiche la collection en tuiles (photo ou 🥃 par défaut, nom, expression, région/type, âge/degré, résumé des statuts, note). Une barre d'outils permet de filtrer par texte libre (nom, distillerie, embouteilleur, marque, expression, région, pays), par type de whisky, par statut de bouteille, ou aux coups de cœur uniquement — le filtrage est instantané (aucune donnée n'est rechargée).

Cliquer sur une tuile ouvre la fiche détail : toutes les informations renseignées, la liste des exemplaires physiques avec leur emplacement et statut, les actions **Ouvrir** / **Terminer** / **Retirer un exemplaire** / **Ajouter un exemplaire**, le suivi du niveau restant pour un exemplaire ouvert, ainsi que **Modifier** et **Supprimer la fiche**.

## Statistiques

Le bouton **📊 Statistiques** ouvre un panneau avec le nombre total de bouteilles, de fiches, la répartition scellées/ouvertes/terminées, le nombre de distilleries distinctes, la valeur du stock restant, l'âge moyen, et des répartitions en barres (pays, région, distillerie, type, tourbé/non tourbé). Les statistiques respectent les filtres actifs à l'écran.

## Entités Home Assistant

Sept capteurs globaux (`sensor.whisky_*`), tous mis à jour en temps réel (pas de polling) :

| Entité | Description | Attributs notables |
|---|---|---|
| `sensor.whisky_total` | Bouteilles (exemplaires physiques), tous statuts | `references` (nb de fiches), `par_pays`, `par_region`, `par_distillerie`, `par_type`, `par_tourbe` |
| `sensor.whisky_opened` | Bouteilles ouvertes | `bottles` : détail par exemplaire ouvert (`whisky_id`, `name`, `slot_idx`, `opened_date`, `days_open`, `remaining_percent`), trié par ancienneté — voir *Automatisations* |
| `sensor.whisky_sealed` | Bouteilles scellées | — |
| `sensor.whisky_finished` | Bouteilles terminées | — |
| `sensor.whisky_distilleries` | Nombre de distilleries distinctes représentées | — |
| `sensor.whisky_collection_value` | Valeur du **stock restant** (scellées + ouvertes ; une bouteille terminée n'a plus de valeur résiduelle et est exclue) | `prix_moyen` |
| `sensor.whisky_average_age` | Âge moyen (années), par fiche — fiches sans âge renseigné ignorées, non pondéré par le nombre d'exemplaires | — |

## Services

Tous documentés avec leurs champs dans `services.yaml` (visibles depuis **Outils de développement → Actions** dans Home Assistant). Résumé :

| Service | Rôle |
|---|---|
| `add_whisky` / `update_whisky` / `remove_whisky` | CRUD d'une fiche |
| `add_slot` / `update_slot` / `move_slot` / `remove_slot` | Gestion des exemplaires physiques d'une fiche |
| `open_bottle` / `finish_bottle` | Cycle de vie scellée → ouverte → terminée |
| `update_remaining` | Suivi manuel du niveau restant (%) d'une bouteille ouverte |
| `add_rack` / `update_rack` / `remove_rack` | Casiers/étagères de rangement |
| `add_cellar` / `rename_cellar` / `remove_cellar` | Collections (plusieurs armoires possibles) |

## Automatisations

Whisky déclenche des événements Home Assistant à chaque changement d'état d'une bouteille, directement utilisables comme déclencheurs d'automatisation (Outils de développement → Automatisations, ou en YAML) :

| Événement | Déclenché par | Données |
|---|---|---|
| `whisky_bottle_added` | `add_whisky` | `whisky_id`, `name` |
| `whisky_bottle_opened` | `open_bottle` | `whisky_id`, `slot_idx`, `name` |
| `whisky_bottle_finished` | `finish_bottle` | `whisky_id`, `slot_idx`, `name` |
| `whisky_bottle_low` | `update_remaining`, uniquement au franchissement du seuil bas (pas à chaque appel) | `whisky_id`, `slot_idx`, `name`, `remaining_percent`, `threshold` |
| `whisky_updated` | tout changement (rafraîchissement carte/capteurs) | — |

Exemple : notifier quand une bouteille passe sous 20 % (seuil par défaut) :

```yaml
automation:
  - alias: "Whisky bientôt vide"
    trigger:
      - platform: event
        event_type: whisky_bottle_low
    action:
      - service: notify.mobile_app_mon_telephone
        data:
          message: >-
            {{ trigger.event.data.name }} n'a plus que
            {{ trigger.event.data.remaining_percent }} % restant.
```

Pour une automatisation basée sur la **durée d'ouverture** d'une bouteille (ex. « une bouteille ouverte depuis plus de 6 mois et toujours pas terminée »), utilisez l'attribut `bottles` de `sensor.whisky_opened` : il liste chaque exemplaire actuellement ouvert avec sa date d'ouverture et son nombre de jours d'ouverture (`days_open`) — pas besoin d'entité dédiée par bouteille.

```yaml
automation:
  - alias: "Whisky ouvert depuis longtemps"
    trigger:
      - platform: time
        at: "09:00:00"
    condition:
      - condition: template
        value_template: >-
          {{ state_attr('sensor.whisky_opened', 'bottles')
             | selectattr('days_open', 'defined')
             | selectattr('days_open', 'gt', 180)
             | list | count > 0 }}
    action:
      - service: notify.mobile_app_mon_telephone
        data:
          message: >-
            {{ state_attr('sensor.whisky_opened', 'bottles')
               | selectattr('days_open', 'gt', 180)
               | map(attribute='name') | join(', ') }}
            ouverte(s) depuis plus de 6 mois.
```

## Reconnaissance photo (IA Gemini) — ce qu'il faut savoir

- **Distillerie ≠ embouteilleur.** Beaucoup de whiskies sont mis en bouteille par un embouteilleur indépendant (Signatory Vintage, Gordon & MacPhail, Cadenhead's, Douglas Laing, Berry Bros. & Rudd, That Boutique-y Whisky Company…), distinct de la distillerie d'origine. Le prompt demande explicitement à l'IA de renseigner les deux champs séparément quand l'étiquette le permet, plutôt que de les confondre.
- **Jamais d'invention.** Un champ que l'IA ne peut pas lire avec confiance sur l'étiquette est renvoyé `null` — jamais une valeur plausible mais devinée. Chaque champ proposé porte un niveau de confiance individuel, plus un score de confiance global.
- **Validation systématique.** Les résultats sont toujours présentés à l'écran avant tout enregistrement ; vous choisissez quels champs appliquer (les champs déjà remplis à la main ne sont jamais pré-cochés). Rien n'est écrit dans votre collection sans cette étape.
- **Aucune dépendance à Whiskybase** (ni à aucune autre base fermée) : les champs `whiskybase_id`/`whiskybase_url` existent uniquement pour un usage manuel optionnel (vous pouvez y coller un lien vous-même) et ne sont **jamais interrogés automatiquement** par l'intégration. Sans clé Gemini configurée, l'ajout se fait entièrement à la main.

## Limites connues (v1)

- Pas de sélecteur d'étagère visuel dans le formulaire de la carte (les services `add_rack`/`add_slot`/`move_slot` existent et fonctionnent, mais leur usage passe par Outils de développement → Actions ou une automatisation tant qu'une UI dédiée n'est pas construite).
- Pas de visualisation 3D de cave, pas de sommelier IA conversationnel — délibérément hors périmètre de cette v1 (voir Statut).
- Capteurs globaux uniquement (pas encore de capteurs par collection pour une installation multi-armoires) — le modèle de données le permet déjà, l'exposition en entités pourra être ajoutée plus tard si le besoin se présente.
- Suite de tests basée sur des stubs Home Assistant maison plutôt que sur un environnement Home Assistant réel (voir `tests/conftest.py`) — rapide et sans dépendance lourde, mais ne remplace pas un test manuel avant mise en production. **Un test manuel dans une vraie instance Home Assistant est recommandé avant utilisation en conditions réelles.**

## Tests

```bash
pip install -r requirements_test.txt
pytest -q
```

La suite (`tests/`) couvre le modèle de données, tous les services (y compris le cycle de vie complet d'une bouteille et le franchissement de seuil de `update_remaining`), les capteurs, et un scénario de non-régression : persistance intégrale des fiches à travers un redémarrage simulé, puis ajout d'une nouvelle fiche sans effet de bord sur les fiches existantes. Les fonctions pures de la carte (`whisky-card.js`) sont testées séparément avec Node — `pytest -q` les exécute aussi automatiquement si Node est installé (voir `tests/test_card_js.py`).

## Licence

Projet open source — voir le fichier [LICENSE](LICENSE). Dérivé de Millésime (MIT, © Redsklns).

# 🥃 Whisky — Collection pour Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=flat-square)](https://github.com/hacs/integration)

**Whisky** transforme Home Assistant en gestionnaire de collection de whiskies : fiches détaillées (distillerie, fûts, tourbe, embouteillage…), reconnaissance d'étiquette par photo (IA Gemini), statistiques et suivi de l'état de chaque bouteille (fermée / ouverte / terminée).

Projet indépendant, dérivé de l'architecture de [Millésime](https://github.com/Redsklns/ha-millesime) (cave à vin) — même style technique, vocabulaire et modèle de données entièrement propres au whisky. Les deux projets sont séparés : aucune donnée, aucune entité, aucun service n'est partagé entre eux.

> 🚧 **En cours de construction.** Ce README et cette intégration sont développés commit par commit ; voir la section Statut ci-dessous pour l'avancement réel.

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
- [ ] Commit 11 — Documentation complète
- [ ] Commit 12 — Packaging final

## Automatisations

Whisky déclenche des événements Home Assistant à chaque changement d'état
d'une bouteille, directement utilisables comme déclencheurs d'automatisation
(Outils de développement → Automatisations, ou en YAML) :

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

Pour une automatisation basée sur la **durée d'ouverture** d'une bouteille
(ex. "une bouteille ouverte depuis plus de 6 mois et toujours pas
terminée"), utilisez l'attribut `bottles` de `sensor.whisky_ouvertes` : il
liste chaque exemplaire actuellement ouvert avec sa date d'ouverture et son
nombre de jours d'ouverture (`days_open`) — pas besoin d'entité dédiée par
bouteille.

```yaml
automation:
  - alias: "Whisky ouvert depuis longtemps"
    trigger:
      - platform: time
        at: "09:00:00"
    condition:
      - condition: template
        value_template: >-
          {{ state_attr('sensor.whisky_ouvertes', 'bottles')
             | selectattr('days_open', 'defined')
             | selectattr('days_open', 'gt', 180)
             | list | count > 0 }}
    action:
      - service: notify.mobile_app_mon_telephone
        data:
          message: >-
            {{ state_attr('sensor.whisky_ouvertes', 'bottles')
               | selectattr('days_open', 'gt', 180)
               | map(attribute='name') | join(', ') }}
            ouverte(s) depuis plus de 6 mois.
```

## Licence

Projet open source — voir le fichier [LICENSE](LICENSE). Dérivé de Millésime (MIT, © Redsklns).

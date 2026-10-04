# Revue complète de la première pièce actuelle — 4 octobre 2026

> Revue historique figée sur la source 0b19465. Les [six familles de défauts ont été corrigées et vérifiées](CURRENT_FIXES.md) à la source 99cf3b3 ; les limites de conception L1–L6 restent distinctes et ne sont pas toutes résolues par cette livraison.

La première pièce fonctionne dans le benchmark publié, mais ses réglages par défaut peuvent empêcher toute recherche de structure avec un seul contexte. Une validation peut aussi bloquer toutes les recherches suivantes si son contexte disparaît. Ces défauts doivent être corrigés avant de confier l’ordonnancement à un coordinateur.

Cette livraison est une **revue avec reproductions**, sans correction du moteur. Les six familles de défauts ci-dessous sont ouvertes. Le budget de recherche non renouvelable et le ralentissement de l’optimiseur sont des limites de conception mesurées séparément.

## Périmètre et preuves

Source figée : [0b19465](https://github.com/Setharkk/Remake-setharkk/commit/0b19465aa6be9aacf291b077cdc69f1b4e44580f). La revue couvre tous les fichiers Python de `first_piece/`, ses sept modules de tests, `setharkk/`, les deux scripts de validation finale, les quatre workflows de la première pièce, ainsi que SPEC, l’architecture et les protocoles de mesure. Les références de présence et d’ordre sont incluses : elles partagent la géométrie et l’adaptateur avec le moteur actuel. Les laboratoires archivés `cortex_lab_v0/` et `cortex_lab_v1/` ne sont pas les moteurs de cette pièce et ne font pas l’objet d’un nouvel audit ici.

- Diagnostic : [9f010f6](https://github.com/Setharkk/Remake-setharkk/commit/9f010f673425645c22edacdcd6189761555d49a7).
- [Exécution Windows/Linux](https://github.com/Setharkk/Remake-setharkk/actions/runs/37217750954) : **85 tests existants réussis et 10 scénarios diagnostiques reproduits sur chaque système**, Python 3.11.16.
- [Sonde reproductible](validation/first_piece_full_review.py), [workflow](.github/workflows/first-piece-review.yml).
- Données exactes : [Windows](first_piece_current_review/windows.json), [Linux](first_piece_current_review/linux.json), [comparaison](first_piece_current_review/comparison.json).
- Les 67 valeurs numériques comparées diffèrent au maximum de **1,44×10⁻¹⁵** ; aucun résultat catégoriel ne diffère. Les durées ne sont pas comparées.
- Les hashes SHA-256 du texte UTF-8 normalisé sont identiques sur les deux systèmes. La sonde vérifie aussi par `git diff` que les fichiers du moteur et des contrats sont inchangés par rapport à la source figée.
- Les artifacts complets sont disponibles dans l’exécution, expiration annoncée le 2 janvier 2027. Les JSON diagnostiques sont aussi conservés dans Git.

Les évaluations de politique finales conservent les identités de symboles et les règles du fixture, mais utilisent de nouveaux tirages d’entrées : graine 71 000 000 + graine du fixture. Les [données du pilote Windows](first_piece_current_review/initial_windows.json) et [Linux](first_piece_current_review/initial_linux.json), [run 37217068378](https://github.com/Setharkk/Remake-setharkk/actions/runs/37217068378), sont conservées séparément : ce pilote réutilisait la graine d’entrée initiale pour évaluer et comptait les hashes d’octets locaux. Ses mesures ne sont pas fusionnées avec le diagnostic final.

Un diagnostic réussi signifie que le défaut décrit a été reproduit ou que son témoin positif fonctionne. Il ne signifie pas que le défaut est corrigé. Les scénarios utilisent des graines fixes : ils établissent des contre-exemples, pas un taux de panne dans toutes les utilisations.

Reproduction à cette source, Python standard uniquement :

```text
python -m unittest discover -s first_piece/tests -v
python -m validation.first_piece_full_review --out current-review.json
```

La sonde refuse un moteur différent de la source relue ; après des corrections futures, revenir au commit diagnostique 9f010f6 pour reproduire cette revue historique.

## Défauts de fonctionnement

P1 = empêche un fonctionnement attendu dans une utilisation normale ; P2 = incohérence fonctionnelle ou état de reprise accepté à tort ; P3 = configuration marginale incompatible avec la reprise.

| Réf. | Priorité | Défaut confirmé | Conséquence |
|---|---|---|---|
| F1 | P1 | Seuil de recherche inaccessible avec un seul contexte par défaut | Les gradients tournent, mais aucune relation n’est cherchée |
| F2 | P1 | Validation sans expiration quand le contexte principal disparaît | Toutes les nouvelles recherches restent bloquées |
| F3 | P2 | Sortie servie et score d’apprentissage différents en mode sans structure | Mesures d’erreur et comparaison au modèle servi incorrectes |
| F4 | P2 | Des invariants de reprise ne sont pas vérifiés | Un état accepté peut contredire les compteurs ou les observations |
| F5 | P2 | Point antipodal accepté alors que sa mise à jour échoue | Prédiction possible, apprentissage impossible sur cette entrée |
| F6 | P3 | Graine acceptée au constructeur puis refusée à la reprise JSON | Configuration autorisée non restaurable |

### F1 — Recherche impossible avec un contexte et les réglages par défaut

Code : [first_piece/shared.py:92](https://github.com/Setharkk/Remake-setharkk/blob/0b19465aa6be9aacf291b077cdc69f1b4e44580f/first_piece/shared.py#L92), [first_piece/shared.py:435](https://github.com/Setharkk/Remake-setharkk/blob/0b19465aa6be9aacf291b077cdc69f1b4e44580f/first_piece/shared.py#L435), [first_piece/shared.py:442](https://github.com/Setharkk/Remake-setharkk/blob/0b19465aa6be9aacf291b077cdc69f1b4e44580f/first_piece/shared.py#L442).

Le constructeur accepte `fit_per_context=256` et `min_records=512`, car il les compare à la capacité maximale de 32 contextes. Or chaque contexte ne conserve que ses 256 derniers épisodes et le déclenchement utilise le **nombre d’épisodes encore conservés**, pas le nombre total reçu. Avec un seul contexte, 512 ne sera jamais atteint, même après un million de retours.

Reproduction `single_context` : 20 000 retours sur un contexte, quatre actions. Le moteur par défaut conserve 256 épisodes, reste en statut `tracking`, réalise **zéro tentative**, et réussit **24,02 %** de 512 épisodes d’évaluation. Le témoin reçoit exactement les mêmes scènes et actions ; seul `min_records=256` change. Il admet une structure et réussit **100 %** des 512 épisodes.

La faible réussite est ici un effet du blocage, avec un témoin causal. Ce n’est pas une conclusion prématurée tirée d’un apprentissage trop court : le seuil est inaccessible par construction. La même situation existe avec d’autres configurations lorsque le nombre de contextes effectivement alimentés est insuffisant. Spécifier `max_tasks=1` en gardant les autres valeurs par défaut échoue même dès la construction.

Correction à préparer : définir un seuil atteignable pour les contextes réellement alimentés, tout en conservant les exigences minimales de support. Le nombre total de retours et le nombre de données disponibles pour ajuster doivent rester deux mesures distinctes. Exposer un statut expliquant le manque de données, plutôt que `tracking` seul.

Critère de sortie : apprentissage vérifié avec `SharedLearner()` et `SharedAdapter()` sur un seul contexte, puis ajout tardif d’un second contexte ; pas d’assouplissement silencieux des tests d’admission.

### F2 — Une validation peut monopoliser la recherche indéfiniment

Code : [first_piece/shared.py:321](https://github.com/Setharkk/Remake-setharkk/blob/0b19465aa6be9aacf291b077cdc69f1b4e44580f/first_piece/shared.py#L321), [first_piece/shared.py:368](https://github.com/Setharkk/Remake-setharkk/blob/0b19465aa6be9aacf291b077cdc69f1b4e44580f/first_piece/shared.py#L368), [first_piece/shared.py:432](https://github.com/Setharkk/Remake-setharkk/blob/0b19465aa6be9aacf291b077cdc69f1b4e44580f/first_piece/shared.py#L432).

Le moteur possède une seule validation globale. Après une première admission, elle est généralement limitée au contexte qui signale une erreur. Seuls les retours de ce contexte font progresser le compteur principal jusqu’aux horizons 128, 1 024 et 4 096. Aucun budget d’attente globale, aucune expiration et aucune annulation de validation ne sont prévus. Tant que `trial` existe, aucune autre recherche ne peut commencer.

Reproduction `disappearing_scope` : acquisition sur deux contextes pendant 10 000 retours ; inversion du contexte 0. Après sept retours de ce contexte, une validation démarre. Le flux passe ensuite exclusivement au contexte 1 pendant **5 000 retours**. Le compteur principal reste **0**, les tentatives restent **2**, le candidat demeure figé et le statut demeure `validating`.

Les poids en service continuent d’apprendre : dans cette reproduction, ils s’adaptent même à l’inversion des sorties du contexte 1. Le défaut concerne donc la disponibilité de la **recherche de nouvelles relations**, et non un arrêt de tous les gradients. Il peut durer sans borne tant que le contexte 0 ne revient pas.

Correction à préparer : cycle de vie explicite de validation, budget d’attente mesuré en observations globales et/ou temps, clôture sans admission lorsqu’un contexte n’est plus alimenté, puis possibilité d’examiner un autre contexte. L’expiration doit être journalisée et conserver le coût statistique de la tentative ; elle ne doit pas recycler silencieusement son budget d’erreur.

Critère de sortie : disparition, retour rare et réapparition du contexte principal, reprise pendant cette attente, plus absence de répétition des examens déjà effectués.

### F3 — Le mode sans structure note une autre prédiction que celle affichée

Code partagé : [first_piece/shared.py:215](https://github.com/Setharkk/Remake-setharkk/blob/0b19465aa6be9aacf291b077cdc69f1b4e44580f/first_piece/shared.py#L215), [first_piece/shared.py:412](https://github.com/Setharkk/Remake-setharkk/blob/0b19465aa6be9aacf291b077cdc69f1b4e44580f/first_piece/shared.py#L412). Même défaut dans la référence temporelle : [first_piece/temporal.py:127](https://github.com/Setharkk/Remake-setharkk/blob/0b19465aa6be9aacf291b077cdc69f1b4e44580f/first_piece/temporal.py#L127), [first_piece/temporal.py:212](https://github.com/Setharkk/Remake-setharkk/blob/0b19465aa6be9aacf291b077cdc69f1b4e44580f/first_piece/temporal.py#L212).

Avec `use_structure=False`, la sortie publique vient de `baseline` et de la route aléatoire. En revanche, `learn` calcule la perte et les gains de validation à partir de `active` et de la route structurée. Après admission, ces deux prédictions peuvent différer fortement.

Reproduction `shared_ablation` : après 10 000 retours, 32 interactions supplémentaires donnent un écart maximal de probabilité de **0,793** entre sortie affichée et valeur renvoyée par `learn`. L’écart maximal de Brier enregistré est **0,631**. Exemple : probabilité servie 0,206 pour un succès ; probabilité notée 0,998 ; erreur servie 0,631 contre une erreur enregistrée de 0,00000234. La sonde temporelle retrouve un écart de Brier de **0,493**.

Les benchmarks principaux entraînent avec `use_structure=True` et lisent les sorties des contrôles dans des évaluations sans apprentissage. Cette reproduction **n’invalide donc pas automatiquement leurs scores publiés**. Elle invalide l’interprétation « erreur du modèle effectivement servi » lors d’un apprentissage avec cette option.

Correction à préparer : distinguer explicitement la sortie servie, l’entraînement des deux banques et les scores comparatifs. Toutes les pertes présentées comme pertes servies doivent utiliser la prédiction effectivement produite avant le retour.

Critère de sortie : cohérence sortie/score dans les deux modes, y compris après admission, pendant une validation et après restauration.

### F4 — La reprise accepte des états qui violent ses propres invariants

Code : [first_piece/shared.py:613](https://github.com/Setharkk/Remake-setharkk/blob/0b19465aa6be9aacf291b077cdc69f1b4e44580f/first_piece/shared.py#L613), [first_piece/shared.py:624](https://github.com/Setharkk/Remake-setharkk/blob/0b19465aa6be9aacf291b077cdc69f1b4e44580f/first_piece/shared.py#L624), [first_piece/adapter.py:278](https://github.com/Setharkk/Remake-setharkk/blob/0b19465aa6be9aacf291b077cdc69f1b4e44580f/first_piece/adapter.py#L278).

La validation des formes, des budgets, du vocabulaire et de nombreuses frontières est réelle. Mais trois vérifications manquent dans la sonde `inconsistent_restore` :

1. Après 512 retours et un ajustement de candidat, augmenter d’une unité un compteur de la banque active est accepté à la restauration. Les sommes active/contrôle ne sont alors plus égales ; le contrôle déjà existant `scale_run.check_bounds` échoue sur cet état.
2. Remplacer l’entrée de recherche par un journal déclarant une tentative 999 999 et un périmètre non lié est accepté. Le journal n’est vérifié que partiellement ; son nombre d’entrées correspond encore au nombre de tentatives.
3. Dans un checkpoint d’adaptateur en phase de lecture, remplacer le dernier symbole enregistré « opaque:a » par « opaque:b » est accepté alors que le vocabulaire et la mémoire restaurés ne contiennent que « opaque:a ». Une rediffusion du prétendu dernier événement serait acquittée comme déjà consommée.

Ces snapshots sont **modifiés manuellement pour tester le validateur**. La revue ne démontre pas leur production par une session normale et ne prétend pas qu’un validateur remplace une signature d’intégrité. Elle démontre des contradictions détectables avec les données déjà présentes dans l’état.

Correction à préparer : vérifier les invariants de compteurs des banques, les champs et la chronologie des recherches/décisions, ainsi que l’appartenance du dernier symbole à la mémoire active. Préserver les checkpoints authentiques déjà publiés et documenter toute évolution de format.

Critère de sortie : refus explicite de ces trois mutations, round-trip identique des états authentiques, et absence de mutation de l’instance d’origine lorsqu’un état est refusé.

### F5 — Un état géométrique accepté ne permet pas toujours une mise à jour

Code : [first_piece/spherical.py:26](https://github.com/Setharkk/Remake-setharkk/blob/0b19465aa6be9aacf291b077cdc69f1b4e44580f/first_piece/spherical.py#L26), [first_piece/spherical.py:39](https://github.com/Setharkk/Remake-setharkk/blob/0b19465aa6be9aacf291b077cdc69f1b4e44580f/first_piece/spherical.py#L39), [first_piece/shared.py:45](https://github.com/Setharkk/Remake-setharkk/blob/0b19465aa6be9aacf291b077cdc69f1b4e44580f/first_piece/shared.py#L45).

La restauration accepte tout point unitaire, dont `[-1,0,0]`, antipode de l’ancre `[1,0,0]`. La prédiction est finie, mais le logarithme géodésique n’y est pas unique ; `update` lève `ValueError: Antipodal logarithm is not unique`.

Reproduction `accepted_antipode` : modification manuelle des points d’une action dans un checkpoint initial de `SharedAdapter`, restauration acceptée, prédiction valide, puis échec du reçu d’apprentissage. La transaction de l’adaptateur revient correctement à son état précédent, mais la même mise à jour restera impossible tant que ce point est servi.

La sonde ne prouve pas que les mises à jour normales atteignent exactement cet antipode. Le défaut est l’incompatibilité entre **domaine accepté à la reprise** et **domaine accepté à l’apprentissage**.

Correction à préparer : domaine numérique annoncé et contrôlé à la restauration, ou traitement géométrique explicite de la singularité. Un déplacement arbitraire ou une projection euclidienne cachée ne suffit pas à préserver l’exigence du réseau.

Critère de sortie : antipodes et voisinages testés, échecs propres si l’état est refusé, gradients et contrainte sphérique conservés sur le domaine accepté.

### F6 — Une graine autorisée ne peut pas être restaurée

Code : [first_piece/shared.py:96](https://github.com/Setharkk/Remake-setharkk/blob/0b19465aa6be9aacf291b077cdc69f1b4e44580f/first_piece/shared.py#L96), [first_piece/shared.py:487](https://github.com/Setharkk/Remake-setharkk/blob/0b19465aa6be9aacf291b077cdc69f1b4e44580f/first_piece/shared.py#L487), [setharkk/contracts.py:27](https://github.com/Setharkk/Remake-setharkk/blob/0b19465aa6be9aacf291b077cdc69f1b4e44580f/setharkk/contracts.py#L27).

Le constructeur accepte toute graine entière positive. Pour `seed=9007199254740993`, il produit un checkpoint JSON que sa restauration refuse : « Large integers must be encoded as strings ». La graine dépasse la borne de 2⁵³−1 imposée par les contrats JSON.

Reproduction `oversized_seed` : construction et sérialisation acceptées, restauration refusée ; une graine ordinaire reprend correctement.

Correction à préparer : borner la graine dès la construction ou la représenter exactement par une chaîne versionnée. Le diagnostic final publie cette graine comme chaîne pour éviter un arrondi lors de la lecture du rapport dans un autre langage. Le pilote initial la publiait comme entier ; son JSON doit être relu avec des entiers exacts.

## Causes des limites actuelles

### L1 — Le temps supplémentaire ne renouvelle pas les tentatives

Code : [first_piece/shared.py:441](https://github.com/Setharkk/Remake-setharkk/blob/0b19465aa6be9aacf291b077cdc69f1b4e44580f/first_piece/shared.py#L441), [first_piece/shared.py:348](https://github.com/Setharkk/Remake-setharkk/blob/0b19465aa6be9aacf291b077cdc69f1b4e44580f/first_piece/shared.py#L348).

Le plafond global par défaut est de seize tentatives sur toute la durée de vie. La sonde `exhausted_budget` donne 20 000 retours sans relation informative, puis 20 000 retours structurés. Les seize essais restent épuisés ; les **40 000 mises à jour supplémentaires** des banques en service ne créent aucune relation. Réussite : **50,59 %**, avec deux actions. Un moteur neuf recevant exactement les mêmes 20 000 scènes structurées réussit **100 %**, avec une admission et une tentative.

C’est une limite annoncée, pas un dépassement accidentel de budget. Prolonger cette instance n’active pas un mécanisme absent. Une remise à zéro naïve des essais réutiliserait aussi l’allocation statistique α=0,05. Une solution doit gérer les ressources et un budget d’erreur sur toute la durée de vie : nouveaux blocs avec allocation summable, état de reprise et journal explicites, ou autre protocole séquentiel justifié. La première pièce conserve l’autorité des décisions ; le coordinateur peut attribuer du calcul et choisir les contextes à alimenter.

### L2 — Le pas diminue avec l’âge du neurone

Code : [first_piece/spherical.py:101](https://github.com/Setharkk/Remake-setharkk/blob/0b19465aa6be9aacf291b077cdc69f1b4e44580f/first_piece/spherical.py#L101).

Le pas vaut `0,03 / sqrt(1+n/100)`. Sans remplacement de banque, il tend vers zéro quand les mises à jour s’accumulent. La sonde `aging` entraîne un neurone sur un succès répété, puis inverse les retours. Il faut **21** retours inversés pour faire passer sa probabilité sous 0,5 après 1 000 anciens retours, et **264** après 100 000. Les pas correspondants sont 0,00905 et 0,000948.

Ce n’est pas une preuve d’impossibilité d’adaptation, ni un bug de gradient : le neurone finit par s’adapter dans cette sonde. C’est un ralentissement mesuré dont une longue session devra tenir compte. Comparer des règles de pas, leurs effets sur le bruit et la rétention, plutôt que choisir un nouveau réglage uniquement pour accélérer ce cas.

### L3 — La garde d’admission ne protège pas une compétence historique

Code : [first_piece/shared.py:417](https://github.com/Setharkk/Remake-setharkk/blob/0b19465aa6be9aacf291b077cdc69f1b4e44580f/first_piece/shared.py#L417), [first_piece/shared.py:389](https://github.com/Setharkk/Remake-setharkk/blob/0b19465aa6be9aacf291b077cdc69f1b4e44580f/first_piece/shared.py#L389).

Le candidat est comparé à la prédiction courante d’une banque active qui continue d’apprendre. Si cette banque a déjà oublié une ancienne compétence, le test de préservation ne compare pas au niveau d’avant changement. Avant qu’un prédicat de contexte soit admis, des épisodes identiques de contextes aux règles contradictoires peuvent utiliser la même route et modifier le même neurone dans des directions opposées. Les buffers ne conservent que les épisodes récents ; une admission remplace aussi les banques par des ajustements sur ces buffers.

Le [benchmark publié](FIRST_PIECE_SCALE_RESULTS.md) montre déjà cette interférence : dans la petite condition, les contextes inchangés tombent à **57,7 % en moyenne** à 1 000 retours après changement, puis récupèrent. Cette revue reprend ce résultat, elle ne présente pas une nouvelle expérience de rétention.

Une protection de compétence ancienne demande un repère conservé et des évaluations de rétention dédiées, avec leur coût compté. Elle ne se déduit pas de la seule garde actuelle.

### L4 — La représentation efface certaines informations et la recherche est incomplète

Code : [first_piece/shared.py:203](https://github.com/Setharkk/Remake-setharkk/blob/0b19465aa6be9aacf291b077cdc69f1b4e44580f/first_piece/shared.py#L203), [first_piece/shared.py:231](https://github.com/Setharkk/Remake-setharkk/blob/0b19465aa6be9aacf291b077cdc69f1b4e44580f/first_piece/shared.py#L231), [first_piece/shared.py:161](https://github.com/Setharkk/Remake-setharkk/blob/0b19465aa6be9aacf291b077cdc69f1b4e44580f/first_piece/shared.py#L161).

La mémoire apprend seulement les présences et l’ordre des premières occurrences. Les épisodes `[a,b,a,a,b]` et `[a,b,b,b,a]` ont la même présence, le même premier ordre et la même longueur ; les nombres de répétitions diffèrent. Le routage et les records ne peuvent pas apprendre une règle qui exige de les distinguer. Le compteur total d’événements n’est pas un comptage par symbole et n’entre pas dans les prédicats.

Le moteur utilise au plus trois prédicats, donc huit routes, dans une bibliothèque programmée. Le pool et le faisceau peuvent exclure une bonne combinaison. Une égalité de contexte ne fournit pas une mémoire indépendante par contexte ; trente-deux contextes configurables ne signifient pas trente-deux règles indépendantes apprenables. Les maximums de 128 symboles et seize actions ne sont pas les échelles du benchmark principal, testé jusqu’à 64 symboles, seize contextes et quatre actions.

Ces limites appartiennent à la première pièce. Ajouter des agents ne lui rendra pas une information effacée ni une relation inexprimable. Une extension de mémoire doit définir les nouvelles observations conservées, leurs budgets, et une migration explicite de checkpoint.

### L5 — La géométrie courbe est effective, sa contribution n’est pas isolée

Les neurones sont des points de S², avec distances géodésiques, gradients tangents et applications exponentielles. Le témoin `geometric_control` compare le gradient à une dérivée numérique : écart **4,47×10⁻¹²**, et une mise à jour diminue l’entropie croisée.

Le cœur reste une banque de probabilités par route/action. La détection des relations provient d’une recherche symbolique discrète ; les symboles ne possèdent pas d’embeddings appris et il n’existe pas de réseau récurrent profond dans cette version. Le contrôle publié retire le routage informatif ; il ne compare pas S² à une banque euclidienne de capacité et budget identiques. On peut donc vérifier le respect de l’exigence non euclidienne sans attribuer les réussites à la courbure ni démontrer un paradigme inédit.

### L6 — Les frontières du laboratoire ne réalisent pas les pièces suivantes

L’apprenant attend des symboles discrets, une frontière d’épisode fournie et un retour binaire. L’exploration uniforme vient des scripts. Les arguments d’action sont vides. L’adaptateur accepte un seul flux et une seule action en attente, avec verrou et cache de reçus borné ; il ne persiste pas automatiquement sur disque.

Le dialogue, les objectifs choisis par le système, le choix d’expériences, les continuations de plusieurs agents et le journal durable d’exécution PC restent à construire. Ce sont des responsabilités des pièces suivantes, sous les contrats communs. Elles ne justifient pas de laisser F1–F3 dans le moteur.

Les scripts d’expérience `scale_run` et `temporal_run` ont également une portée de laboratoire : certaines valeurs CLI non positives ou répétées ne sont pas refusées, certaines écritures de résultats/checkpoints ne sont pas atomiques, et il n’existe pas de reprise automatique du run. Ne pas les employer comme journal durable d’une session PC. Les validations finales téléchargent des artifacts de runs fixes : leur expiration et l’absence de contrôle complet de version nécessitent une gestion explicite avant d’en faire une pipeline permanente.

## Pourquoi les 85 tests ne détectaient pas ces défauts

| Domaine | Couverture existante relue | Lacune confirmée par la revue |
|---|---|---|
| Géométrie | Norme, tangence, rotation, formes et mise à jour | Domaine antipodal accepté à la reprise |
| Apprentissage partagé | Combinaisons, XOR, transfert, changement, banques figées | Réglages par défaut avec un seul contexte ; contexte de validation absent |
| Ablations | Lecture de copies sans apprendre pendant l’évaluation | Apprentissage réel avec `use_structure=False` |
| Reprise | RNG, ordre, banques figées, vocabulaire, budgets, prédiction en attente | Invariants croisés et journal de recherche partiellement vérifiés |
| Interfaces | Séquences, identité, reçus répétés, concurrence, refus transactionnels | Dernier symbole du checkpoint incompatible avec la mémoire |
| Mesures | Holdouts sans gradients, contrôles de même capacité, bruit | Longue vie après exhaustion ; vieillissement du pas ; avantage géométrique non comparé |

Le test à un seul contexte fournit explicitement `min_records=256` ; le benchmark observe au moins deux contextes. Ils évitent donc F1. Le test d’horizons scoped conserve le contexte principal ; il ne couvre pas F2. Les échelles et les sorties évaluées correspondent aux conditions publiées ; leur réussite ne valide pas automatiquement les autres configurations.

## Ordre de correction et raccord aux prochaines pièces

1. **F1 et F2 : disponibilité de l’apprentissage structurel.** Rendre le cas par défaut atteignable et gérer la clôture des validations qui n’avancent plus. Le futur coordinateur doit recevoir un état explicite : collecte, validation, attente de contexte, clôture ou épuisement.
2. **F3–F6 : cohérence des mesures et de la reprise.** Fixer les invariants que le coordinateur pourra considérer comme fiables ; préserver l’unité du score et l’identité du modèle réellement servi.
3. **L1 : protocole renouvelable de recherche.** Compter les coûts et le risque dans des blocs persistants ; reprise en plein bloc, bruit prolongé puis signal, plusieurs changements et absence de faux renouvellement après restauration.
4. **L2–L4 : adaptation longue et rétention.** Mesurer une courbe par âge et contexte, puis justifier les extensions de mémoire/recherche nécessaires. Une limite d’expression doit être distinguée d’un simple délai d’acquisition.
5. **Deuxième pièce minimale.** Construire l’ordonnancement et le journal sur des états dont la progression, les scores et la reprise sont cohérents. Les objectifs et le dialogue restent des expériences séparées.

La revue fournit des critères de sortie et des causes identifiées. Elle ne garantit pas l’absence de tout autre bug. Aucune correction du moteur, aucun cortex autonome et aucune exécution d’application réelle ne sont livrés dans cette étape.


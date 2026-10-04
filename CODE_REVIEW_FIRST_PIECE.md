# Revue du code de la première pièce

La revue a trouvé **trois familles de défauts corrigées**, reproduites par
sept cas avant/après : la couverture des deux décisions statistiques, les
calculs numériques extrêmes et la perte des horizons évalués lors d'une
interruption. Les **20 tests passent sous Windows et Linux**.

Le code reste un laboratoire et un critère d'évaluation. Il ne contient
pas encore la mémoire apprenante ou le nouveau réseau non euclidien.

- Version examinée : [c929d0d](https://github.com/Setharkk/Remake-setharkk/commit/c929d0d0ea534c6d7f4d37cd5b432c450128c9ed).
- Corrections : [ccbf2d7](https://github.com/Setharkk/Remake-setharkk/commit/ccbf2d723de3a901259e7586f2e442e94a7ea0b7).
- Vérifications : [Actions 37199893904](https://github.com/Setharkk/Remake-setharkk/actions/runs/37199893904).
- Portée : monde, critère, audit, tests, workflow et documentation.
- Les prototypes V0/V1 et les résultats historiques sont conservés.

## Défauts corrigés

### 1. P2 — Risque statistique commun aux deux queues

La fonction accepte une proposition avec une borne inférieure et la
rejette avec une borne supérieure. La formule initiale allouait
alpha/M à chaque queue. Leur union donnait une garantie globale de
2*alpha pour M comparaisons, alors que le budget annoncé était alpha.

La correction emploie :

~~~text
delta = log(1/epsilon) * sqrt(2 * log(2*M/alpha) / n)
~~~

Le contrôle calcule la somme des bornes de Hoeffding : elle passe de
0.10 à 0.05, à l'arrondi près. Ce calcul concerne la garantie théorique ;
il ne mesure pas une fréquence réelle de 10 % d'erreurs.

Voir [criterion.py, calcul de la borne](https://github.com/Setharkk/Remake-setharkk/blob/ccbf2d723de3a901259e7586f2e442e94a7ea0b7/first_piece/criterion.py#L65).

Cette garantie suppose toujours des prédictions figées, des données IID
et un maximum déclaré de comparaisons. La fonction est sans état :
le futur protocole devra réellement faire respecter ces conditions et
compter les comparaisons.

### 2. P2 — Entrées numériques valides donnant des infinis ou une exception

Les réglages ci-dessous étaient acceptés par la validation d'entrée :

| Reproduction | Avant | Après |
|---|---|---|
| alpha = 1e-310 | Borne infinie par débordement de M/alpha | Borne finie |
| epsilon = 1e-310 | Borne infinie par débordement de 1/epsilon | Borne finie |
| M = 10**400 | OverflowError | Borne finie |
| epsilon = 1e-20, prédiction 1 et résultat 0 | ValueError : log(0) | Score borné fini |
| Pénalité 1e308, coût de deux unités | Coût infini transmis au résultat | ValueError explicite |

Les logarithmes sont calculés séparément, sans former les rapports
susceptibles de déborder. Le score borne directement la probabilité du
résultat observé : avec un epsilon minuscule, 1-epsilon peut être arrondi
à 1, donc borner d'abord p puis calculer 1-p n'était pas suffisant.
Un coût non représentable est rejeté avant la décision.

Voir [criterion.py, score et validation](https://github.com/Setharkk/Remake-setharkk/blob/ccbf2d723de3a901259e7586f2e442e94a7ea0b7/first_piece/criterion.py#L22).

Ces cas extrêmes ne décrivent pas les réglages courants de l'audit.
Ils vérifient que des valeurs admises par l'API ne produisent pas
silencieusement des résultats non finis.

### 3. P2 — Les mesures des horizons atteints disparaissaient lors d'une interruption

Une interruption injectée après 125 interactions laisse 125 observations
JSONL. Avant correction, les mesures de l'horizon 100 n'existaient que
dans la mémoire du processus. Le snapshot du monde et le résumé de la
condition étaient écrits uniquement à sa fin.

Chaque horizon évalué est maintenant conservé dans progress.json :
mesures, état du monde correspondant et nombre d'interactions à cette
frontière. Ce fichier est remplacé atomiquement. L'interruption simulée
conserve l'horizon 100 et marque la condition interrupted.

Voir [audit.py, sauvegarde des horizons](https://github.com/Setharkk/Remake-setharkk/blob/ccbf2d723de3a901259e7586f2e442e94a7ea0b7/first_piece/audit.py#L77).

Seul completed indique une condition terminée. Un arrêt brutal peut
laisser running ; ce statut doit être traité comme incomplet. Les
mesures peuvent être perdues entre deux horizons, et cette correction
ne prétend pas garantir la persistance face à toute panne matérielle.

Le snapshot restaure le monde au dernier horizon évalué. Les accumulateurs
et le générateur des actions de l'audit ne sont pas restaurés : il ne
s'agit pas d'une commande de reprise complète de l'audit ou d'un apprenant.

## Limites structurantes avant de construire l'apprenant

### Le gain ne démontre pas la nécessité de la distinction

Une reproduction fait dépendre le résultat de l'action seule et donne
deux groupes équilibrés sans lien avec le résultat. Une nouvelle
prédiction mieux ajustée est néanmoins acceptée.

C'est un gain prédictif réel, mais il ne prouve pas que la partition
apporte quelque chose. Le test d'admission ne devra pas servir seul à
attribuer ce gain à une distinction.

Le futur apprenant aura besoin d'un contrôle sans cette distinction,
ajusté avec les mêmes informations et le même budget. Cette comparaison
n'est pas implémentée puisque le mécanisme qui construit les distinctions
ne l'est pas encore. La reproduction est conservée dans les preuves.

### Le monde fournit l'historique en une fois

observe() livre la liste complète des événements passés. Le laboratoire
permet de tester une relation avec cet historique accessible ; il ne
teste pas encore le maintien d'un état interne pendant l'arrivée des
événements. Une tâche délivrant les événements un à un sera nécessaire
si l'on veut mesurer une mémoire temporelle interne.

### Aucun apprentissage neuronal n'est présent

Les prédictions de l'audit viennent d'un oracle qui connaît la règle.
Aucun paramètre neuronal n'est entraîné, aucune distinction n'est
découverte et aucun apprentissage autonome n'est mesuré.

La géométrie non euclidienne du futur réseau, la rétention, la reprise
de l'apprenant et les objectifs autonomes restent à construire.
Ce constat est une limite de cette étape, pas une conclusion sur
l'impossibilité de réaliser le projet.

## Validation exécutée

- Python 3.11, bibliothèque standard.
- 20 tests par système : les 14 précédents et six nouveaux tests couvrant
  les calculs extrêmes, les deux queues et la conservation des horizons.
- Les sept reproductions échouent sur la version examinée et réussissent
  après correction, sur Windows et Linux.
- Les preuves avant/après sont identiques entre les systèmes.
- Nouvel audit : cinq graines, deux présentations, deux mondes, soit
  20 conditions et 200 000 interactions générées par système.
- Les résumés des audits concordent après exclusion du temps écoulé.
  Les deux systèmes rejouent les mêmes graines.

| Interactions par condition | Dix conditions structurées | Dix conditions aléatoires |
|---:|---|---|
| 100 | En attente | En attente |
| 1 000 | Acceptées | Rejetées |
| 10 000 | Acceptées | Rejetées |

Avec la correction, les bornes d'incertitude valent 2.120043, 0.670416
et 0.212004 aux trois horizons. Le gain structuré de l'oracle reste
0.683097 nat par interaction. Les décisions de l'audit initial restent
donc les mêmes malgré la borne légèrement plus prudente.

Ces nombres décrivent des contrôles du laboratoire, sans courbe
d'apprentissage d'un modèle.

## Preuves conservées et reproduction

- [Avant/après Windows](first_piece_reviews/run_37199893904/proof_windows.json).
- [Avant/après Linux](first_piece_reviews/run_37199893904/proof_linux.json).
- [Audit Windows](first_piece_reviews/run_37199893904/audit_windows.json).
- [Audit Linux](first_piece_reviews/run_37199893904/audit_linux.json).
- Les archives Actions contiennent les preuves et les observations complètes ;
  elles ont une durée de conservation limitée.

Dans un clone avec l'historique Git complet :

~~~text
python -m unittest discover -s first_piece/tests -v
python -m first_piece.review_probe --out revue-premiere-piece.json
python -m first_piece.audit --out first_piece/lab_runs/apres_revue
~~~

Le fichier [review_probe.py](first_piece/review_probe.py) charge la version
examinée depuis son commit Git pour la comparer au code corrigé.
Le chemin de sortie de l'audit doit être neuf.

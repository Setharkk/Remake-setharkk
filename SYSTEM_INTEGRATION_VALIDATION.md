# Validation des contrats et du raccordement de la première pièce

Le commit testé est [`d34efaa1450e2b4e286daa16f5e645de49589d94`](https://github.com/Setharkk/Remake-setharkk/commit/d34efaa1450e2b4e286daa16f5e645de49589d94).
Le [workflow 37206180993](https://github.com/Setharkk/Remake-setharkk/actions/runs/37206180993) est terminé avec succès
sous Windows et Ubuntu, Python 3.11, bibliothèque standard uniquement.

Cette modification prépare les frontières du système décrites dans
l'[architecture](SYSTEM_ARCHITECTURE.md). Elle n'implémente pas encore
l'[apprenant temporel suivant](FIRST_PIECE_NEXT_PROTOCOL.md), des objectifs
autonomes ou des opérations sur les applications du PC.

## Tests et boucle d'intégration

**51 tests réussis par système**, dont les 35 tests précédents et 16 nouveaux
tests : 5 pour les contrats communs, 11 pour l'adaptateur.

| Vérification | Résultat Windows/Linux |
|---|---|
| Messages génériques et actions avec arguments | Acceptés sans imposer le vocabulaire binaire du laboratoire |
| Versions inconnues, valeurs non JSON, doublons de candidats | Refusés |
| Ordre, flux, contextes et capacités incompatibles | Refus sans publication d'un état partiel |
| Prédictions détachées et propositions anciennes | Mutation extérieure sans effet ; proposition périmée refusée |
| Deux agents proposant simultanément | Une seule requête en attente dans l'état central |
| Résultat répété ou contradictoire | Aucun double apprentissage ; contradiction refusée |
| Résultat ancien après éviction du cache | Refus sans nouvelle mise à jour |
| Exécution échouée ou annulée | Épisode fermé sans étiquette d'entraînement inventée |
| Checkpoint au milieu des événements ou avec action en attente | Reprise JSON exacte |
| Format ou état de reprise incohérent | Refus |

La sonde indépendante utilise la graine 0, **1 344 interactions** et
**7 431 événements sensoriels**. Deux agents simulés proposent chacun
672 actions dans le même contexte. L'exécuteur synthétique est appelé
1 344 fois et la révision atteint 1 344.

À chaque interaction, les probabilités et le checkpoint neuronal complet,
y compris l'état aléatoire et les modèles figés, sont identiques à ceux de
l'apprenant direct recevant les mêmes événements, actions et résultats.

La distinction est admise à 1 280 interactions ; la sonde poursuit ensuite
64 interactions. Elle couvre donc la collecte, la validation figée et
l'admission. Le modèle effectue 1 855 mises à jour neuronales en incluant
les deux ajustements temporaires.

Une reprise JSON intervient après une action déjà réalisée pendant la
validation, avant la livraison de son résultat. Le test conserve ce
résultat en dehors de l'apprenant, reprend sa requête et livre deux fois
le même résultat. Il n'exécute pas l'action une seconde fois et n'applique
qu'un apprentissage. Un test supplémentaire compare le modèle direct
sur 416 interactions avec la graine 3.

Cette simulation ne prouve pas une exécution physique unique après une
panne du PC. Un journal durable de coordinateur et d'exécuteur reste à
construire avant des actions réelles.

## Absence de régression de l'expérience précédente

Le workflow réexécute les cinq graines, les trois modes, les horizons
100/1 000/10 000, le transfert, la rétention et la reprise du protocole
d'[apprentissage précédent](FIRST_PIECE_LEARNING_RESULTS.md).

Les sorties sont comparées à celles du run 37202478630, en excluant les
durées d'exécution. Pour chaque système :

- 4 241 valeurs numériques comparées ;
- écart maximal par rapport à sa sortie précédente : **0** ;
- aucune différence de structure, de décision ou de résultat non numérique.

Entre Windows et Linux, le maximum des écarts du protocole d'apprentissage
est 9.33e-15, inférieur à la tolérance de 1e-10. Les résultats de la sonde
d'intégration sont identiques, y compris ses 48 valeurs numériques.

Le grand protocole utilise encore l'apprenant direct. La parité via
l'adaptateur est vérifiée sur les 1 344 interactions de la sonde et les
416 du test, pas sur toutes les interactions du grand protocole.
L'algorithme d'apprentissage et sa géométrie n'ont pas été modifiés.

## Preuves conservées et portée

Les résultats lisibles restent versionnés :

- [Windows](system_integration_results/run_37206180993/windows.json) ;
- [Linux](system_integration_results/run_37206180993/linux.json) ;
- [Comparaisons](system_integration_results/run_37206180993/comparison.json).

Les artefacts du workflow contiennent aussi les rapports d'intégration
et les checkpoints complets de l'expérience d'apprentissage.

Les messages et l'adaptateur version 1 sont implémentés. Les limites de
flux, d'actions et de contextes sont annoncées comme capacités du prototype.
La génération des objectifs, la planification, l'essaim autonome, la
mémoire neuronale partagée et la gestion durable des actions restent des
pièces distinctes à construire et vérifier.

La première pièce ne lit toujours pas l'ordre des symboles et ne retente
pas une distinction rejetée. Le prochain protocole fixe les mesures et
les exigences de remplacement dans un même contexte ; ces capacités
ne sont pas obtenues par le seul ajout de contrats.

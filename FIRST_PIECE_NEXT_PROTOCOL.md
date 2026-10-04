# Prochaine révision de la première pièce : ordre et remplacement

Ce protocole est la prochaine expérience à implémenter. Le modèle actuel
reste un apprenant de présence. Les [contrats communs](SYSTEM_ARCHITECTURE.md)
sont préparés pour que cette révision n'oblige pas les agents à manipuler
sa mémoire interne.

## Question mesurable

Le modèle peut-il apprendre une relation d'ordre, puis s'adapter à une
nouvelle règle dans le même contexte observable, sous un budget borné,
en préservant les autres compétences encore valides ?

Le contexte reste identique pendant le changement. L'environnement ne
transmet ni numéro de régime, ni règle, ni annonce du changement à
l'apprenant. Le journal d'évaluation conserve ces informations séparément.

## Monde temporel minimal

Chaque épisode contient une occurrence de A, une occurrence de B, et des
distracteurs. L'ordre A puis B ou B puis A est équilibré. La présence des
symboles et leur nombre sont identiques : seul l'ordre apporte l'information.

~~~text
r = 1 si A précède B, sinon 0
résultat = 1 si action == (r XOR règle_cachée), sinon 0
~~~

La règle cachée est fixe durant la première phase, puis inversée dans
le même contexte. Le transfert allonge les délais et change les distracteurs.
Une condition sans changement mesure les effets du temps seul ; des
conditions bruit et action seule vérifient que des structures inutiles
ne sont pas conservées automatiquement.

L'inversion choisit volontairement un cas où les mêmes observations
changent de résultat. La mémoire doit conserver les autres compétences
encore valides, pas prédire simultanément deux étiquettes contradictoires
sans information permettant de les distinguer.

## État à rendre effectivement révisable

La nouvelle famille de distinctions doit lire l'ordre en ligne, avec
un état borné plutôt qu'un historique illimité. Son vocabulaire et son
coût seront définis avant les mesures. Le réseau neuronal conserve des
paramètres et opérations sur une géométrie courbe.

Un candidat reste distinct du modèle actif durant sa comparaison.
Une mauvaise proposition ne doit pas détruire le modèle utilisé.
Après rejet, une nouvelle tentative devient possible dans un budget
explicite. Lors d'un remplacement, l'ancien état est libéré ou compte
dans le budget s'il est retenu ; créer une nouvelle tâche cachée n'est
pas une solution admissible.

La révision du modèle reste liée aux résultats appris. Les détails de
la distinction et de ses essais restent privés à l'apprenant ; les agents
utilisent les prédictions et identifiants communs.

## Mesures et budgets avant exécution

Les horizons primaires sont 100, 1 000 et 10 000 interactions d'apprentissage
avant et après le changement. Les résultats précoces donnent une courbe,
pas une conclusion définitive d'impossibilité. Si le résultat demeure
incertain à 10 000, il est déclaré inconclusif pour cette exposition.

Les futurs réglages préciseront avant exécution :
le nombre maximal de propositions, de points neuronaux actifs et temporaires,
la mémoire d'événements et de validation, les mises à jour et les évaluations.
Le budget doit inclure le contrôle, les modèles figés, les journaux et
l'éventuel état conservé pour rétention.

Les actions d'acquisition restent aléatoires dans cette expérience afin
d'isoler l'apprentissage. Le choix autonome des expériences sera une pièce
ultérieure avec son propre contrôle.

Contrôles appariés : apprenant de présence actuel, nouvelle mémoire avec
apprentissage structurel désactivé, et interventions sur l'ordre. Ils
reçoivent les mêmes événements, actions et résultats. Les écarts de
budget doivent être publiés ; un contrôle moins entraîné ne justifie
pas une conclusion sur la mémoire.

Les évaluations utilisent des mondes indépendants et des modèles figés,
sans mises à jour. On mesure la perte probabiliste, le succès d'action,
les essais rejetés/admis, le délai de récupération après changement,
les coûts cumulés et la rétention d'un autre contexte encore valide.
Plusieurs graines et les différences appariées sont publiées.

## Validation quand la règle change

Le critère IID de l'expérience de présence ne doit pas être repris comme
preuve de stabilité future sur un bloc mélangeant deux régimes.
Le candidat et le contrôle restent figés pendant une comparaison.

La gestion des fenêtres et la règle de redémarrage seront fixées avant
l'expérience, avec un budget global des essais et de leurs horizons.
Un détecteur éventuel utilise uniquement les résultats passés visibles
au modèle. L'évaluateur ne lui transmet pas la date cachée du changement.

Une comparaison couvrant une dérive peut mesurer un gain moyen sur son
bloc ; elle ne démontre pas que ce gain persiste dans le régime actuel.
Le protocole devra soit justifier une borne adaptée à ses dépendances,
soit réserver les affirmations statistiques aux évaluations indépendantes
de régimes fixes. Tout arrêt ou essai supplémentaire est compté.

## Critères pour passer à la pièce suivante

- La courbe montre un apprentissage de l'ordre au-delà du contrôle de présence.
- Une inversion sans nouveau contexte produit une récupération mesurée,
  ou une limite explicitement reproduite et attribuée à son mécanisme.
- Le budget total reste borné pendant les tentatives et remplacements.
- Une reprise JSON conserve une relation temporelle et un essai en cours.
- Les mêmes contrats de prédictions, propositions et résultats restent utilisés.
- Aucune conclusion générale d'autonomie ne repose sur cette seule tâche.

Aucun de ces résultats temporels n'est encore revendiqué. Le travail
présent fixe les frontières et les vérifications nécessaires pour que
la prochaine modification de l'apprenant s'insère dans le même système.

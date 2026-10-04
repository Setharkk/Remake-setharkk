# Recherche renouvelable et rétention — protocole fixé avant exécution

Le moteur sphérique et le contrat observation → prédiction → action → reçu restent
ceux de la première pièce. Le mode renouvelable doit rendre possible une nouvelle
recherche après l'épuisement des 16 tentatives du mode historique, sans effacer les
poids, les observations récentes ou le risque déjà alloué.

## Risque et mémoire

Un bloc e contient B tentatives (16 par défaut). Pour un modèle neuf :
alpha_e = 0,05 / [e(e+1)]. La somme sur tous les blocs vaut 0,05.
Les trois comparaisons et trois horizons 128, 1 024 et 4 096 conservent leur
allocation interne et la borne uniforme dans le temps du complément.
Aucune tentative refusée, expirée ou sans hypothèse ne rembourse du risque.

Un import explicite du moteur fini conserve son premier budget historique 0,05.
Les futurs blocs se partagent un budget supplémentaire 0,05 :
alpha_1 = 0,05 ; alpha_e = 0,05 / [e(e-1)] pour e >= 2.
La borne historique + future est donc 0,10, annoncée dans les métriques.
Il serait incorrect de réécrire les décisions anciennes avec le budget neuf.

Le journal détaillé conserve seulement le bloc courant : au plus B recherches et
3B décisions. Un résumé de préfixe conserve les tentatives, les ajustements, les
admissions, les clôtures et la dernière admission nécessaires aux compteurs et
à la reprise. Les expériences exportent leur journal détaillé à l'extérieur du
modèle. Un résumé n'est pas une archive intégrale ni une preuve cryptographique.

## Expériences

Trois graines fixées 0, 1, 2 ; mêmes événements et mêmes actions exploratoires
uniformes pour le moteur fini et le moteur renouvelable. 16 symboles opaques,
4 contextes, 4 actions, mêmes capacités et optimiseur ; seule la politique du
budget diffère. Le risque initial du mode renouvelable est volontairement plus
strict. Comparaison synthétique ; aucun avantage de courbure n'est testé.

1. Bruit avant compétence : 40 000 retours sans relation symboles/résultat,
   puis 40 000 retours de règle structurée. Le résultat aléatoire est Bernoulli(1/4),
   indépendant de l'action et des symboles. Contrôler admissions sous bruit,
   tentatives au-delà de 16 et succès final sur 2 048 épisodes nouveaux.
2. Rétention : 20 000 retours structurés, puis 80 000 retours de bruit,
   puis 40 000 retours de retour à la même règle. Évaluer avant le bruit, tous les
   20 000 retours de bruit et tous les 2 000 retours de récupération.
   Distinguer conservation pendant le bruit et réapprentissage ensuite.
3. Changements successifs : 40 000 retours initiaux, puis six changements
   représentables de la règle du seul contexte 0. Décalages modulo 4 :
   0 → 1 → 2 → 3 → 0 → 2 → 1. 40 000 retours par état, soit 10 000 par contexte.
   Mesurer chaque contexte séparément tous les 4 000 retours. Les contextes 1–3
   restent inchangés. Consigner les délais d'admission et la précision transitoire,
   sans confondre une admission avec la première récupération de compétence.

Les évaluations utilisent un flux indépendant, sans apprentissage, sur une copie
du modèle. La mesure principale est le succès de l'action de probabilité maximale ;
le score de Brier moyen est aussi exporté. La référence de succès aléatoire vaut
0,25. Chaque point de courbe utilise 512 épisodes nouveaux par contexte ; les
frontières de phase utilisent 2 048 épisodes au total. La quantité de retours
appris, globale et par contexte, est l'unité principale ; les durées CPU sont
secondaires. L'évaluation ne consomme pas les données d'entraînement.

## Critères et limites annoncés avant les résultats

Exiger : reprise exacte après renouvellement, invariants de compteurs et de risque,
journaux bornés, aucune admission observée dans les trois contrôles de bruit,
et compétence finale >= 95 % après bruit initial pour les trois graines.
Exporter toutes les courbes de rétention et de changement, y compris les baisses ;
ne pas exiger une absence d'oubli que ce mécanisme ne promet pas.

Ce renouvellement ne protège pas les poids actifs des gradients du bruit.
L'horizon de validation maximal reste 4 096 retours principaux : un risque de plus
en plus petit peut rendre une amélioration trop faible indécidable à cet horizon.
Les garanties statistiques portent sur les gains logarithmiques bornés, sous les
conditions de prévisibilité du protocole ; pas sur toutes les actions futures.
Ni les règles de l'environnement, ni une capacité autonome générale ne sont
apprises ou démontrées par ce seul banc d'essai.

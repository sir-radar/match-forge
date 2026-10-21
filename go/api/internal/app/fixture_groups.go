package app

import (
	"sort"
	"strconv"
	"strings"
	"unicode"

	"golang.org/x/text/cases"
	"golang.org/x/text/unicode/norm"
)

type fixtureGroupDimensions struct {
	typeName string
	season   string
	division string
}

type fixtureGroupCluster struct {
	group       FixtureGroup
	dimensions  fixtureGroupDimensions
	competition map[string]struct{}
	fixtures    map[string]struct{}
}

func mergeFixtureGroups(groups []FixtureGroup, selectedCompetitionID string) []FixtureGroup {
	buckets := collectFixtureClusters(groups)
	merged := []FixtureGroup{}
	for _, clusters := range buckets {
		merged = append(merged, mergeCompetitionBucket(clusters, selectedCompetitionID)...)
	}
	sort.Slice(merged, func(i, j int) bool {
		left, right := merged[i].Competition, merged[j].Competition
		if left.Continent != right.Continent {
			return left.Continent < right.Continent
		}
		if left.Country != right.Country {
			return left.Country < right.Country
		}
		if left.Name != right.Name {
			return left.Name < right.Name
		}
		if left.Season != right.Season {
			return left.Season < right.Season
		}
		return left.ID < right.ID
	})
	return merged
}

func collectFixtureClusters(groups []FixtureGroup) map[string][]*fixtureGroupCluster {
	buckets := map[string][]*fixtureGroupCluster{}
	for _, group := range groups {
		competition := group.Competition
		nameKey := competitionNameKey(competition.Country, competition.Name)
		if nameKey == "" {
			nameKey = normalizeCompetitionText(competition.ID)
		}
		bucketKey := strings.Join([]string{
			normalizeCompetitionText(competition.Country), nameKey,
		}, "\x00")
		dimensions := fixtureGroupDimensions{
			typeName: knownCompetitionValue(competition.Type),
			season:   knownCompetitionValue(competition.Season),
		}
		if competition.Division != nil {
			dimensions.division = strconv.Itoa(*competition.Division)
		}
		clusters := buckets[bucketKey]
		matching := findFixtureCluster(clusters, dimensions)
		if matching == nil {
			matching = &fixtureGroupCluster{
				group:       FixtureGroup{Competition: competition},
				dimensions:  dimensions,
				competition: map[string]struct{}{},
				fixtures:    map[string]struct{}{},
			}
			buckets[bucketKey] = append(clusters, matching)
		}
		mergeFixtureGroupInto(matching, group)
	}
	return buckets
}

func findFixtureCluster(clusters []*fixtureGroupCluster, dimensions fixtureGroupDimensions) *fixtureGroupCluster {
	for _, cluster := range clusters {
		if cluster.dimensions == dimensions {
			return cluster
		}
	}
	return nil
}

func mergeCompetitionBucket(clusters []*fixtureGroupCluster, selectedCompetitionID string) []FixtureGroup {
	sort.Slice(clusters, func(i, j int) bool {
		if clusters[i].dimensions != clusters[j].dimensions {
			return dimensionsKey(clusters[i].dimensions) < dimensionsKey(clusters[j].dimensions)
		}
		return clusters[i].group.Competition.ID < clusters[j].group.Competition.ID
	})
	targets := clusterTargets(clusters)
	for index := range clusters {
		target := fixtureClusterRoot(targets, index)
		if target != index {
			mergeFixtureCluster(clusters[target], clusters[index])
		}
	}
	merged := []FixtureGroup{}
	for index, cluster := range clusters {
		if fixtureClusterRoot(targets, index) != index || !containsCompetition(cluster, selectedCompetitionID) {
			continue
		}
		sort.Slice(cluster.group.Fixtures, func(i, j int) bool {
			if !cluster.group.Fixtures[i].KickoffAt.Equal(cluster.group.Fixtures[j].KickoffAt) {
				return cluster.group.Fixtures[i].KickoffAt.Before(cluster.group.Fixtures[j].KickoffAt)
			}
			return cluster.group.Fixtures[i].ID < cluster.group.Fixtures[j].ID
		})
		merged = append(merged, cluster.group)
	}
	return merged
}

func clusterTargets(clusters []*fixtureGroupCluster) []int {
	targets := make([]int, len(clusters))
	for index := range targets {
		targets[index] = index
	}
	for source := range clusters {
		if candidate := uniqueMoreSpecificCluster(clusters, source); candidate >= 0 {
			targets[source] = candidate
		}
	}
	return targets
}

func uniqueMoreSpecificCluster(clusters []*fixtureGroupCluster, source int) int {
	specificity := dimensionsSpecificity(clusters[source].dimensions)
	bestSpecificity, bestTarget, bestCount := specificity, -1, 0
	for candidate, other := range clusters {
		if candidate == source || !dimensionsCompatible(clusters[source].dimensions, other.dimensions) {
			continue
		}
		candidateSpecificity := dimensionsSpecificity(other.dimensions)
		if candidateSpecificity > bestSpecificity {
			bestSpecificity, bestTarget, bestCount = candidateSpecificity, candidate, 1
		} else if candidateSpecificity == bestSpecificity && candidateSpecificity > specificity {
			bestCount++
		}
	}
	if bestCount == 1 {
		return bestTarget
	}
	return -1
}

func containsCompetition(cluster *fixtureGroupCluster, selectedCompetitionID string) bool {
	if selectedCompetitionID == "" {
		return true
	}
	_, exists := cluster.competition[selectedCompetitionID]
	return exists
}

func mergeFixtureGroupInto(target *fixtureGroupCluster, source FixtureGroup) {
	if target.group.Competition.ID == "" || preferCompetition(source.Competition, target.group.Competition) {
		target.group.Competition = source.Competition
	}
	if source.Competition.ID != "" {
		target.competition[source.Competition.ID] = struct{}{}
	}
	for _, fixture := range source.Fixtures {
		if _, exists := target.fixtures[fixture.ID]; exists {
			continue
		}
		target.fixtures[fixture.ID] = struct{}{}
		target.group.Fixtures = append(target.group.Fixtures, fixture)
	}
}

func mergeFixtureCluster(target, source *fixtureGroupCluster) {
	if preferCompetition(source.group.Competition, target.group.Competition) {
		target.group.Competition = source.group.Competition
	}
	for id := range source.competition {
		target.competition[id] = struct{}{}
	}
	for _, fixture := range source.group.Fixtures {
		if _, exists := target.fixtures[fixture.ID]; exists {
			continue
		}
		target.fixtures[fixture.ID] = struct{}{}
		target.group.Fixtures = append(target.group.Fixtures, fixture)
	}
}

func preferCompetition(candidate, current Competition) bool {
	candidateScore, currentScore := competitionSpecificity(candidate), competitionSpecificity(current)
	if candidateScore != currentScore {
		return candidateScore > currentScore
	}
	if candidate.Name != current.Name {
		return candidate.Name < current.Name
	}
	return candidate.ID < current.ID
}

func competitionSpecificity(competition Competition) int {
	score := 0
	if knownCompetitionValue(competition.Type) != "" {
		score++
	}
	if knownCompetitionValue(competition.Season) != "" {
		score++
	}
	if competition.Division != nil {
		score++
	}
	return score
}

func dimensionsSpecificity(dimensions fixtureGroupDimensions) int {
	score := 0
	for _, value := range []string{dimensions.typeName, dimensions.season, dimensions.division} {
		if value != "" {
			score++
		}
	}
	return score
}

func dimensionsCompatible(left, right fixtureGroupDimensions) bool {
	return compatibleValue(left.typeName, right.typeName) &&
		compatibleValue(left.season, right.season) &&
		compatibleValue(left.division, right.division)
}

func compatibleValue(left, right string) bool {
	return left == "" || right == "" || left == right
}

func dimensionsKey(dimensions fixtureGroupDimensions) string {
	return strings.Join([]string{dimensions.typeName, dimensions.season, dimensions.division}, "\x00")
}

func fixtureClusterRoot(targets []int, index int) int {
	for targets[index] != index {
		index = targets[index]
	}
	return index
}

func knownCompetitionValue(value string) string {
	value = normalizeCompetitionText(value)
	if value == "" || value == "unknown" || value == "n a" {
		return ""
	}
	return value
}

func competitionNameKey(country, name string) string {
	key := normalizeCompetitionName(name)
	if normalizeCompetitionText(country) == "saudi arabia" {
		switch key {
		case "division 1", "first division", "saudi first division", "saudi arabia first division":
			return "saudi first division"
		}
	}
	if normalizeCompetitionText(country) == "egypt" && key == "egyptian premier league" {
		return "premier league"
	}
	return key
}

func normalizeCompetitionName(value string) string {
	key := normalizeCompetitionText(value)
	if strings.HasPrefix(key, "the ") {
		key = strings.TrimPrefix(key, "the ")
	}
	switch key {
	case "laliga":
		return "la liga"
	case "j league":
		return "j1 league"
	case "j league 2":
		return "j2 league"
	case "liga nacional apertura":
		return "liga nacional"
	case "league one":
		return "league 1"
	case "league two":
		return "league 2"
	case "first division":
		return "division 1"
	case "second division":
		return "division 2"
	}
	return key
}

func normalizeCompetitionText(value string) string {
	folded := cases.Fold().String(norm.NFKD.String(strings.TrimSpace(value)))
	var words strings.Builder
	space := true
	for _, character := range folded {
		if unicode.Is(unicode.Mn, character) || unicode.Is(unicode.Me, character) || unicode.Is(unicode.Mc, character) {
			continue
		}
		if unicode.IsLetter(character) || unicode.IsDigit(character) {
			words.WriteRune(character)
			space = false
		} else if !space {
			words.WriteByte(' ')
			space = true
		}
	}
	return strings.TrimSpace(words.String())
}

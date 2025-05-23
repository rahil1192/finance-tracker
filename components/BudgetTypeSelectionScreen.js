import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useNavigation } from '@react-navigation/native';

export default function BudgetTypeSelectionScreen() {
  const navigation = useNavigation();

  const handleGroupBudget = () => {
    // Navigate to create group budget form
    navigation.navigate('CreateBudgetForm', { type: 'group' });
  };

  const handlePersonalBudget = () => {
    // Navigate to create personal budget form
    navigation.navigate('CreateBudgetForm', { type: 'personal' });
  };

  return (
    <SafeAreaView style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity 
          onPress={() => navigation.goBack()} 
          style={styles.backButton}
        >
          <Ionicons name="arrow-back" size={24} color="#0284c7" />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Create Budget</Text>
        <View style={styles.placeholderView} />
      </View>

      <ScrollView style={styles.content} contentContainerStyle={styles.contentContainer}>
        {/* Group Budget Option */}
        <TouchableOpacity 
          style={styles.budgetTypeCard}
          onPress={handleGroupBudget}
        >
          <Text style={styles.budgetTypeTitle}>Group Budget</Text>
          <View style={styles.iconContainer}>
            <Ionicons name="people" size={48} color="#0284c7" />
            <Ionicons name="add" size={20} color="#0284c7" style={styles.addIcon} />
          </View>
          <Text style={styles.budgetTypeDescription}>
            Budgeting together creates a sense of belonging and responsibility
          </Text>
        </TouchableOpacity>

        {/* OR Divider */}
        <View style={styles.dividerContainer}>
          <Text style={styles.dividerText}>OR</Text>
        </View>

        {/* Personal Budget Option */}
        <TouchableOpacity 
          style={styles.budgetTypeCard}
          onPress={handlePersonalBudget}
        >
          <Text style={styles.budgetTypeTitle}>Personal Budget</Text>
          <View style={styles.iconContainer}>
            <Ionicons name="person" size={48} color="#0284c7" />
            <Ionicons name="add" size={20} color="#0284c7" style={styles.addIcon} />
          </View>
          <Text style={styles.budgetTypeDescription}>
            Empowers financial control, fosters savings and support goal achievement
          </Text>
        </TouchableOpacity>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: 'white',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 12,
    backgroundColor: '#e0f2fe',
  },
  headerTitle: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#1e293b',
  },
  backButton: {
    padding: 4,
  },
  placeholderView: {
    width: 32,
  },
  content: {
    flex: 1,
  },
  contentContainer: {
    paddingVertical: 24,
    paddingHorizontal: 16,
  },
  budgetTypeCard: {
    borderWidth: 1,
    borderColor: '#e2e8f0',
    borderRadius: 16,
    padding: 24,
    alignItems: 'center',
  },
  budgetTypeTitle: {
    fontSize: 22,
    fontWeight: 'bold',
    color: '#1e293b',
    marginBottom: 16,
  },
  iconContainer: {
    position: 'relative',
    marginBottom: 16,
  },
  addIcon: {
    position: 'absolute',
    bottom: 0,
    right: -5,
  },
  budgetTypeDescription: {
    fontSize: 16,
    color: '#64748b',
    textAlign: 'center',
    lineHeight: 24,
  },
  dividerContainer: {
    alignItems: 'center',
    marginVertical: 24,
  },
  dividerText: {
    fontSize: 18,
    color: '#94a3b8',
    fontWeight: '500',
  },
});
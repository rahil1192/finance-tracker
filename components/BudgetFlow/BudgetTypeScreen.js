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

export default function BudgetTypeScreen() {
  const navigation = useNavigation();

  const handleExpenseBudget = () => {
    navigation.navigate('BudgetDetailsScreen', { budgetType: 'Expense' });
  };

  const handleIncomeBudget = () => {
    navigation.navigate('BudgetDetailsScreen', { budgetType: 'Income' });
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
        {/* Expense Budget Option */}
        <TouchableOpacity 
          style={styles.budgetTypeCard}
          onPress={handleExpenseBudget}
        >
          <Text style={styles.budgetTypeTitle}>Expense Budget</Text>
          <View style={styles.iconContainer}>
            <Ionicons name="arrow-up" size={32} color="#f97316" />
          </View>
          <Text style={styles.budgetTypeDescription}>
            Track and control where your money goes.
          </Text>
        </TouchableOpacity>

        {/* OR Divider */}
        <View style={styles.dividerContainer}>
          <Text style={styles.dividerText}>OR</Text>
        </View>

        {/* Income Budget Option */}
        <TouchableOpacity 
          style={styles.budgetTypeCard}
          onPress={handleIncomeBudget}
        >
          <Text style={styles.budgetTypeTitle}>Income Budget</Text>
          <View style={styles.iconContainer}>
            <Ionicons name="arrow-down" size={32} color="#22c55e" />
          </View>
          <Text style={styles.budgetTypeDescription}>
            Plan and manage your income streams.
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
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: '#f1f5f9',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 16,
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
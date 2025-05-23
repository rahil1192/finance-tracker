import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useNavigation, useRoute } from '@react-navigation/native';

export default function BudgetScreen() {
  const [activeTab, setActiveTab] = useState('BUDGETS');
  const [budgetType, setBudgetType] = useState('Expenses');
  const [currentMonth, setCurrentMonth] = useState('May');
  const [budgets, setBudgets] = useState([]);
  
  const navigation = useNavigation();
  const route = useRoute();

  // Check if we need to refresh the budgets list
  useEffect(() => {
    if (route.params?.refresh) {
      // In a real app, you would fetch budgets from storage or API
      // For now, we'll just simulate adding a new budget
      setBudgets([
        {
          id: '1',
          name: 'Hi',
          type: 'Expense',
          amount: 45,
          spent: 0,
          repeat: 'Monthly',
          startDate: 'May 1',
        },
        ...budgets
      ]);
    }
  }, [route.params?.refresh]);

  const handlePreviousMonth = () => {
    // Logic to go to previous month
    console.log('Previous month');
  };

  const handleNextMonth = () => {
    // Logic to go to next month
    console.log('Next month');
  };

  const openCreateBudgetFlow = () => {
    // Navigate to budget type selection screen
    navigation.navigate('BudgetTypeSelection');
  };

  const openHelpGuide = () => {
    // Open help guide
    console.log('Open help guide');
  };

  const renderBudgetsList = () => {
    if (budgets.length === 0) {
      return (
        <>
          {/* Empty State Card */}
          <View style={styles.emptyStateCard}>
            <Text style={styles.emptyStateTitle}>Start Saving with a Smart Budget</Text>
            <Text style={styles.emptyStateDescription}>
              Create a budget to control your spending rather wondering where the money goes.
            </Text>
            <TouchableOpacity 
              style={styles.createBudgetButton}
              onPress={openCreateBudgetFlow}
            >
              <Text style={styles.createBudgetButtonText}>+ Create Budget</Text>
            </TouchableOpacity>
          </View>

          {/* Help Link */}
          <TouchableOpacity 
            style={styles.helpLinkContainer}
            onPress={openHelpGuide}
          >
            <Text style={styles.helpLinkText}>How to create my first budget?</Text>
          </TouchableOpacity>
        </>
      );
    }

    return (
      <View style={styles.budgetsList}>
        {budgets.map(budget => (
          <View key={budget.id} style={styles.budgetCard}>
            <View style={styles.budgetCardHeader}>
              <View style={styles.budgetIconContainer}>
                <Ionicons 
                  name={budget.type === 'Expense' ? 'arrow-up' : 'arrow-down'} 
                  size={24} 
                  color={budget.type === 'Expense' ? '#f97316' : '#22c55e'} 
                />
              </View>
              <View style={styles.budgetInfo}>
                <Text style={styles.budgetName}>{budget.name}</Text>
                <Text style={styles.budgetRepeat}>{budget.repeat} • Starting {budget.startDate}</Text>
              </View>
              <Text style={styles.budgetAmount}>${budget.amount}</Text>
            </View>
            <View style={styles.budgetProgress}>
              <View style={styles.progressBar}>
                <View 
                  style={[
                    styles.progressFill, 
                    { width: `${(budget.spent / budget.amount) * 100}%` }
                  ]} 
                />
              </View>
              <View style={styles.budgetStats}>
                <Text style={styles.budgetSpent}>$0 spent</Text>
                <Text style={styles.budgetRemaining}>${budget.amount} remaining</Text>
              </View>
            </View>
          </View>
        ))}
      </View>
    );
  };

  return (
    <SafeAreaView style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity>
          <Ionicons name="menu" size={24} color="#0284c7" />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Budget</Text>
        <View style={styles.headerIcons}>
          <TouchableOpacity style={styles.iconButton} onPress={openCreateBudgetFlow}>
            <Ionicons name="add" size={24} color="#0284c7" />
          </TouchableOpacity>
          <TouchableOpacity style={styles.iconButton}>
            <Ionicons name="options" size={24} color="#0284c7" />
          </TouchableOpacity>
        </View>
      </View>

      {/* Tab Navigation */}
      <View style={styles.tabContainer}>
        {['BUDGETS', 'GOALS'].map((tab) => (
          <TouchableOpacity
            key={tab}
            style={[
              styles.tab,
              activeTab === tab && styles.activeTab
            ]}
            onPress={() => setActiveTab(tab)}
          >
            <Text
              style={[
                styles.tabText,
                activeTab === tab && styles.activeTabText
              ]}
            >
              {tab}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      <ScrollView style={styles.content}>
        {/* Budget Type Toggle */}
        <View style={styles.toggleContainer}>
          <TouchableOpacity
            style={[
              styles.toggleButton,
              budgetType === 'Expenses' && styles.activeToggleButton
            ]}
            onPress={() => setBudgetType('Expenses')}
          >
            <Text
              style={[
                styles.toggleText,
                budgetType === 'Expenses' && styles.activeToggleText
              ]}
            >
              Expenses
            </Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[
              styles.toggleButton,
              budgetType === 'Income' && styles.activeToggleButton
            ]}
            onPress={() => setBudgetType('Income')}
          >
            <Text
              style={[
                styles.toggleText,
                budgetType === 'Income' && styles.activeToggleText
              ]}
            >
              Income
            </Text>
          </TouchableOpacity>
          
          {/* Month Navigation */}
          <View style={styles.monthNavigation}>
            <TouchableOpacity onPress={handlePreviousMonth}>
              <Ionicons name="chevron-back" size={24} color="#64748b" />
            </TouchableOpacity>
            <Text style={styles.monthText}>{currentMonth}</Text>
            <TouchableOpacity onPress={handleNextMonth}>
              <Ionicons name="chevron-forward" size={24} color="#64748b" />
            </TouchableOpacity>
          </View>
        </View>

        {renderBudgetsList()}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#e0f2fe',
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
    fontSize: 22,
    fontWeight: 'bold',
    color: '#1e293b',
  },
  headerIcons: {
    flexDirection: 'row',
  },
  iconButton: {
    marginLeft: 16,
  },
  tabContainer: {
    flexDirection: 'row',
    backgroundColor: 'white',
    borderBottomWidth: 1,
    borderBottomColor: '#e2e8f0',
  },
  tab: {
    flex: 1,
    paddingVertical: 16,
    alignItems: 'center',
  },
  activeTab: {
    borderBottomWidth: 2,
    borderBottomColor: '#0284c7',
  },
  tabText: {
    fontSize: 14,
    fontWeight: '500',
    color: '#64748b',
  },
  activeTabText: {
    color: '#0284c7',
  },
  content: {
    flex: 1,
  },
  toggleContainer: {
    flexDirection: 'row',
    paddingHorizontal: 16,
    paddingVertical: 16,
    alignItems: 'center',
  },
  toggleButton: {
    paddingHorizontal: 20,
    paddingVertical: 8,
    borderRadius: 20,
    marginRight: 8,
  },
  activeToggleButton: {
    backgroundColor: '#dbeafe',
  },
  toggleText: {
    fontSize: 16,
    color: '#64748b',
  },
  activeToggleText: {
    color: '#0284c7',
    fontWeight: '500',
  },
  monthNavigation: {
    flexDirection: 'row',
    alignItems: 'center',
    marginLeft: 'auto',
  },
  monthText: {
    fontSize: 16,
    fontWeight: '500',
    color: '#1e293b',
    marginHorizontal: 8,
  },
  emptyStateCard: {
    margin: 16,
    padding: 24,
    backgroundColor: 'white',
    borderRadius: 16,
    alignItems: 'center',
  },
  emptyStateTitle: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#1e293b',
    textAlign: 'center',
    marginBottom: 12,
  },
  emptyStateDescription: {
    fontSize: 16,
    color: '#64748b',
    textAlign: 'center',
    marginBottom: 24,
  },
  createBudgetButton: {
    borderWidth: 1,
    borderColor: '#0284c7',
    borderRadius: 24,
    paddingVertical: 12,
    paddingHorizontal: 24,
  },
  createBudgetButtonText: {
    fontSize: 16,
    color: '#0284c7',
    fontWeight: '500',
  },
  helpLinkContainer: {
    alignItems: 'center',
    marginTop: 24,
    marginBottom: 40,
  },
  helpLinkText: {
    fontSize: 16,
    color: '#4b6bfb',
    fontWeight: '500',
  },
  budgetsList: {
    paddingHorizontal: 16,
    paddingBottom: 24,
  },
  budgetCard: {
    backgroundColor: 'white',
    borderRadius: 16,
    padding: 16,
    marginBottom: 16,
  },
  budgetCardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 16,
  },
  budgetIconContainer: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: '#f1f5f9',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
  },
  budgetInfo: {
    flex: 1,
  },
  budgetName: {
    fontSize: 16,
    fontWeight: 'bold',
    color: '#1e293b',
  },
  budgetRepeat: {
    fontSize: 14,
    color: '#64748b',
  },
  budgetAmount: {
    fontSize: 16,
    fontWeight: 'bold',
    color: '#1e293b',
  },
  budgetProgress: {
    marginTop: 8,
  },
  progressBar: {
    height: 8,
    backgroundColor: '#e2e8f0',
    borderRadius: 4,
    marginBottom: 8,
  },
  progressFill: {
    height: 8,
    backgroundColor: '#0284c7',
    borderRadius: 4,
  },
  budgetStats: {
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  budgetSpent: {
    fontSize: 14,
    color: '#64748b',
  },
  budgetRemaining: {
    fontSize: 14,
    color: '#64748b',
  },
});
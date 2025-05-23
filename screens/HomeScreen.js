import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  TextInput,
  StatusBar,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { FontAwesome5 } from '@expo/vector-icons';
import { MaterialCommunityIcons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';


export default function HomeScreen({ navigation }) {
   // Get the safe area insets
   const insets = useSafeAreaInsets();
   const [transactions, setTransactions] = useState([]);
   const [summary, setSummary] = useState(null);
   const [loading, setLoading] = useState(true);

   useEffect(() => {
     fetchTransactions();
   }, []);

   const fetchTransactions = async () => {
     try {
       const response = await fetch('http://192.168.2.19:8000/api/transactions');
       const data = await response.json();
       setTransactions(data);

       const summaryResponse = await fetch('http://192.168.2.19:8000/api/transactions/summary');
       const summaryData = await summaryResponse.json();
       setSummary(summaryData);
     } catch (error) {
       console.error('Error fetching transactions:', error);
     } finally {
       setLoading(false);
     }
   };
  
   // Calculate bottom padding to account for tab bar
   // Tab bar height is typically around 50-60px plus any safe area insets
   const bottomTabHeight = 60 + insets.bottom;
  return (
    <View style={styles.container}>
      {/* Top Navigation */}
      <View style={[styles.header, { paddingTop: insets.top }]}>
        <TouchableOpacity>
          <Ionicons name="menu" size={24} color="#0284c7" />
        </TouchableOpacity>
        <View style={styles.searchContainer}>
          <Ionicons name="search" size={20} color="gray" style={styles.searchIcon} />
          <TextInput
            style={styles.searchInput}
            placeholder="Search"
            placeholderTextColor="gray"
          />
        </View>
        <TouchableOpacity style={styles.iconButton}>
          <Ionicons name="notifications" size={24} color="#0284c7" />
        </TouchableOpacity>
        <TouchableOpacity style={styles.iconButton}>
          <Ionicons name="help-circle" size={24} color="#0284c7" />
        </TouchableOpacity>
      </View>

      {/* Greeting */}
      <View style={styles.greeting}>
        <View style={styles.profileCircle}>
          <Text style={styles.profileInitial}>r</Text>
        </View>
        <View style={styles.greetingText}>
          <Text style={styles.greetingMessage}>Hi rahil shah, Good afternoon!</Text>
        </View>
      </View>

      <ScrollView 
        style={styles.scrollView}
        contentContainerStyle={styles.scrollViewContent}
        showsVerticalScrollIndicator={false}
      >
        {/* Transactions Summary Card */}
        <View style={styles.card}>
          <View style={styles.cardHeader}>
            <Text style={styles.cardTitle}>Transaction Summary</Text>
            <Ionicons name="chevron-forward" size={20} color="gray" />
          </View>
          <View style={styles.cardContent}>
            {loading ? (
              <Text>Loading...</Text>
            ) : summary ? (
              <>
                <View style={styles.summaryRow}>
                  <Text style={styles.summaryLabel}>Income:</Text>
                  <Text style={[styles.summaryAmount, styles.positiveAmount]}>
                    ${summary.total_income.toFixed(2)}
                  </Text>
                </View>
                <View style={styles.summaryRow}>
                  <Text style={styles.summaryLabel}>Expenses:</Text>
                  <Text style={[styles.summaryAmount, styles.negativeAmount]}>
                    ${summary.total_expenses.toFixed(2)}
                  </Text>
                </View>
                <View style={styles.summaryRow}>
                  <Text style={styles.summaryLabel}>Net Balance:</Text>
                  <Text style={[
                    styles.summaryAmount,
                    summary.net_balance >= 0 ? styles.positiveAmount : styles.negativeAmount
                  ]}>
                    ${summary.net_balance.toFixed(2)}
                  </Text>
                </View>
              </>
            ) : (
              <Text>No transaction data available</Text>
            )}
          </View>
        </View>

        {/* Recent Transactions Card */}
        <View style={styles.card}>
          <View style={styles.cardHeader}>
            <Text style={styles.cardTitle}>Recent Transactions</Text>
            <Ionicons name="chevron-forward" size={20} color="gray" />
          </View>
          <View style={styles.cardContent}>
            {loading ? (
              <Text>Loading...</Text>
            ) : transactions.length > 0 ? (
              transactions.slice(0, 5).map((transaction, index) => (
                <View key={index} style={styles.transactionRow}>
                  <View style={styles.transactionInfo}>
                    <Text style={styles.transactionDescription}>
                      {transaction.description}
                    </Text>
                    <Text style={styles.transactionCategory}>
                      {transaction.category}
                    </Text>
                  </View>
                  <Text style={[
                    styles.transactionAmount,
                    transaction.type === 'income' ? styles.positiveAmount : styles.negativeAmount
                  ]}>
                    ${transaction.amount.toFixed(2)}
                  </Text>
                </View>
              ))
            ) : (
              <Text>No recent transactions</Text>
            )}
          </View>
        </View>

        {/* Accounts */}
        <View style={styles.card}>
          <View style={styles.cardHeader}>
            <Text style={styles.cardTitle}>Accounts</Text>
            <Ionicons name="chevron-forward" size={20} color="gray" />
          </View>
          <View style={styles.cardContent}>
            <View style={styles.bankIcon}>
              <MaterialCommunityIcons name="bank" size={40} color="#90CAF9" />
            </View>
            <Text style={styles.cardText}>Link your account to pull transactions</Text>
            <Text style={styles.cardText}>automatically.</Text>
            <TouchableOpacity style={styles.addButton}>
              <Ionicons name="add" size={16} color="#0284c7" />
              <Text style={styles.addButtonText}>Add Account</Text>
            </TouchableOpacity>
          </View>
          <View style={styles.dotContainer}>
            <View style={[styles.dot, styles.activeDot]} />
            <View style={styles.dot} />
            <View style={styles.dot} />
          </View>
        </View>

        {/* Bills */}
        <View style={styles.card}>
          <View style={styles.cardHeader}>
            <Text style={styles.cardTitle}>Bills</Text>
            <Ionicons name="chevron-forward" size={20} color="gray" />
          </View>
          <View style={styles.cardContent}>
            <View style={styles.iconContainer}>
              <Ionicons name="receipt" size={32} color="#00B0FF" />
            </View>
            <Text style={styles.cardText}>Add recurring bills & subscriptions</Text>
            <Text style={styles.cardText}>to get payment reminders.</Text>
            <TouchableOpacity 
              style={styles.textButton}
              onPress={() => navigation.navigate('Bills')}
            >
              <Text style={styles.textButtonLabel}>+ Add Bill</Text>
            </TouchableOpacity>
          </View>
          <View style={styles.dotContainer}>
            <View style={[styles.dot, styles.activeDot]} />
            <View style={styles.dot} />
          </View>
        </View>

        {/* Top Expenses */}
        <View style={styles.card}>
          <View style={styles.cardHeader}>
            <View>
              <Text style={styles.cardTitle}>Top Expenses</Text>
              <Text style={styles.cardSubtitle}>|| May</Text>
            </View>
            <Ionicons name="chevron-forward" size={20} color="gray" />
          </View>
          <View style={[styles.cardContent, styles.expenseContent]}>
            <View style={styles.donutChart}>
              {/* This is a simplified donut chart */}
              <View style={styles.donutChartInner} />
            </View>
            <View style={styles.expenseDetails}>
              <View style={styles.expenseCategory}>
                <View style={styles.categoryIcon}>
                  <Ionicons name="document-text" size={16} color="gray" />
                </View>
                <Text style={styles.categoryText}>Bills & Utilities</Text>
              </View>
              <View style={styles.expenseAmount}>
                <Text style={styles.amountText}>$90</Text>
                <Ionicons name="chevron-forward" size={16} color="gray" />
              </View>
            </View>
          </View>
          <View style={styles.dotContainer}>
            <View style={[styles.dot, styles.activeDot]} />
            <View style={styles.dot} />
          </View>
        </View>

        {/* Budget */}
        <View style={styles.card}>
          <View style={styles.cardHeader}>
            <Text style={styles.cardTitle}>Budget</Text>
            <Ionicons name="chevron-forward" size={20} color="gray" />
          </View>
          <View style={styles.cardContent}>
            <View style={styles.iconContainer}>
              <FontAwesome5 name="dollar-sign" size={24} color="#00B0FF" />
            </View>
            <Text style={styles.cardText}>Tap to create your first budget.</Text>
            <TouchableOpacity 
              style={styles.textButton}
              onPress={() => navigation.navigate('Budget')}
            >
              <Text style={styles.textButtonLabel}>+ Create Budget</Text>
            </TouchableOpacity>
          </View>
        </View>

        {/* Cash Flow */}
        <View style={styles.card}>
          <View style={styles.cardHeader}>
            <Text style={styles.cardTitle}>Cash Flow</Text>
            <Ionicons name="chevron-forward" size={20} color="gray" />
          </View>
          <View style={styles.cashFlowContent}>
            <View style={styles.cashFlowRow}>
              <Text style={styles.periodText}>May</Text>
              <View style={styles.amountContainer}>
                <Text style={styles.percentText}>0.0%</Text>
                <Text style={styles.positiveAmount}>+ $0</Text>
              </View>
            </View>
            <View style={styles.progressBar} />
            <View style={styles.cashFlowRow}>
              <Text style={styles.periodText}>Monthly</Text>
              <View style={styles.amountContainer}>
                <Text style={styles.negativePercent}>↑ 100.0%</Text>
                <Text style={styles.negativeAmount}>- $90</Text>
              </View>
            </View>
            <View style={styles.balanceContainer}>
              <Text style={styles.balanceText}>Projected Balance of</Text>
              <Text style={styles.negativeBalance}>- $90</Text>
            </View>
          </View>
        </View>

        {/* Goals */}
        <View style={styles.card}>
          <View style={styles.cardHeader}>
            <Text style={styles.cardTitle}>Goals</Text>
            <Ionicons name="chevron-forward" size={20} color="gray" />
          </View>
          <View style={styles.cardContent}>
            <View style={styles.iconContainer}>
              <Ionicons name="target" size={32} color="#00B0FF" />
            </View>
            <Text style={styles.cardText}>Tap to create your first goal.</Text>
            <TouchableOpacity style={styles.textButton}>
              <Text style={styles.textButtonLabel}>+ Create Goal</Text>
            </TouchableOpacity>
          </View>
        </View>
      </ScrollView>

      {/* Floating Action Button */}
      <TouchableOpacity style={[styles.fab, { bottom: 40 }]}>
        <Ionicons name="add" size={30} color="white" />
      </TouchableOpacity>
    </View>
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
    paddingHorizontal: 16,
    paddingVertical: 12,
    backgroundColor: '#e0f2fe',
    zIndex: 1,
  },
  searchContainer: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'white',
    borderRadius: 20,
    marginHorizontal: 8,
    paddingHorizontal: 8,
  },
  searchIcon: {
    marginLeft: 8,
  },
  searchInput: {
    flex: 1,
    height: 40,
    paddingHorizontal: 8,
  },
  iconButton: {
    marginLeft: 8,
  },
  greeting: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 16,
    backgroundColor: '#bae6fd',
    borderBottomLeftRadius: 24,
    borderBottomRightRadius: 24,
    marginBottom: 16,
  },
  profileCircle: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: '#0284c7',
    justifyContent: 'center',
    alignItems: 'center',
  },
  profileInitial: {
    color: 'white',
    fontSize: 18,
    fontWeight: 'bold',
  },
  greetingText: {
    marginLeft: 12,
  },
  greetingMessage: {
    fontSize: 16,
    fontWeight: '500',
    color: '#1e293b',
  },
  scrollView: {
    flex: 1,
  },
  scrollViewContent: {
    paddingHorizontal: 16,
    paddingBottom: 100, // Add extra padding at bottom to ensure content is visible above tab bar
  },
  card: {
    backgroundColor: 'white',
    borderRadius: 16,
    marginBottom: 16,
    padding: 16,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 2,
    elevation: 2,
  },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 16,
  },
  cardTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#1e293b',
  },
  cardSubtitle: {
    fontSize: 14,
    color: '#64748b',
  },
  cardContent: {
    alignItems: 'center',
    paddingVertical: 16,
  },
  bankIcon: {
    marginBottom: 8,
  },
  iconContainer: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: '#e1f5fe',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 8,
  },
  cardText: {
    fontSize: 16,
    color: '#64748b',
    textAlign: 'center',
    marginBottom: 4,
  },
  addButton: {
    flexDirection: 'row',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#0284c7',
    borderRadius: 20,
    paddingHorizontal: 16,
    paddingVertical: 8,
    marginTop: 16,
  },
  addButtonText: {
    color: '#0284c7',
    marginLeft: 4,
  },
  textButton: {
    marginTop: 16,
  },
  textButtonLabel: {
    color: '#0284c7',
    fontSize: 16,
  },
  dotContainer: {
    flexDirection: 'row',
    justifyContent: 'center',
    marginTop: 8,
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: '#e2e8f0',
    marginHorizontal: 2,
  },
  activeDot: {
    backgroundColor: '#94a3b8',
  },
  expenseContent: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'flex-start',
    paddingHorizontal: 0,
  },
  donutChart: {
    width: 64,
    height: 64,
    borderRadius: 32,
    borderWidth: 8,
    borderColor: '#1e40af',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 16,
  },
  donutChartInner: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: 'white',
  },
  expenseDetails: {
    flex: 1,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  expenseCategory: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  categoryIcon: {
    width: 24,
    height: 24,
    borderRadius: 4,
    backgroundColor: '#e2e8f0',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 8,
  },
  categoryText: {
    fontSize: 16,
    color: '#334155',
  },
  expenseAmount: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  amountText: {
    fontSize: 16,
    fontWeight: '600',
    marginRight: 4,
  },
  cashFlowContent: {
    paddingVertical: 8,
  },
  cashFlowRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginVertical: 8,
  },
  periodText: {
    fontSize: 16,
    color: '#334155',
  },
  amountContainer: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  percentText: {
    fontSize: 14,
    color: '#64748b',
    marginRight: 8,
  },
  positiveAmount: {
    fontSize: 16,
    fontWeight: '600',
    color: '#10b981',
  },
  negativePercent: {
    fontSize: 14,
    color: '#ef4444',
    marginRight: 8,
  },
  negativeAmount: {
    fontSize: 16,
    fontWeight: '600',
    color: '#1e293b',
  },
  progressBar: {
    height: 8,
    backgroundColor: '#fbbf24',
    borderRadius: 4,
    marginVertical: 8,
  },
  balanceContainer: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#e2e8f0',
    borderRadius: 8,
    padding: 12,
    marginTop: 8,
  },
  balanceText: {
    fontSize: 16,
    color: '#1e293b',
  },
  negativeBalance: {
    fontSize: 16,
    color: '#ef4444',
    marginLeft: 4,
  },
  fab: {
    position: 'absolute',
    bottom: 100, // Increased spacing to position higher above tab bar
    right: 16,
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: '#0284c7',
    justifyContent: 'center',
    alignItems: 'center',
    elevation: 4,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.25,
    shadowRadius: 3.84,
  },
  summaryRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginVertical: 4,
  },
  summaryLabel: {
    fontSize: 16,
    color: '#64748b',
  },
  summaryAmount: {
    fontSize: 16,
    fontWeight: '600',
  },
  transactionRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: '#e2e8f0',
  },
  transactionInfo: {
    flex: 1,
  },
  transactionDescription: {
    fontSize: 16,
    color: '#1e293b',
  },
  transactionCategory: {
    fontSize: 14,
    color: '#64748b',
  },
  transactionAmount: {
    fontSize: 16,
    fontWeight: '600',
  },
});
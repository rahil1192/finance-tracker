import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
} from 'react-native';
import Slider from '@react-native-community/slider';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useNavigation, useRoute } from '@react-navigation/native';

export default function BudgetReviewScreen() {
  const navigation = useNavigation();
  const route = useRoute();
  const { 
    budgetType, 
    budgetName, 
    budgetAmount, 
    repeatFrequency, 
    startDate, 
    rolloverBudget, 
    alertPercentage 
  } = route.params;

  const handleCreate = () => {
    // Save budget logic would go here
    navigation.navigate('Budget', { refresh: true });
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
        <Text style={styles.headerTitle}>Review Budget</Text>
        <View style={styles.placeholderView} />
      </View>

      <ScrollView style={styles.content}>
        {/* Budget Icon and Name */}
        <View style={styles.budgetHeader}>
          <View style={styles.budgetIconContainer}>
            <Ionicons name="wallet" size={40} color="#0284c7" />
          </View>
          <Text style={styles.budgetName}>{budgetName}</Text>
          <Text style={styles.budgetType}>{budgetType} (Personal)</Text>
        </View>

        {/* Budget Details */}
        <View style={styles.detailsContainer}>
          {/* Amount */}
          <View style={styles.detailRow}>
            <Text style={styles.detailLabel}>Amount</Text>
            <Text style={styles.detailValue}>${budgetAmount}</Text>
          </View>
          <View style={styles.separator} />

          {/* Repeat */}
          <View style={styles.detailRow}>
            <Text style={styles.detailLabel}>Repeat</Text>
            <Text style={styles.detailValue}>
              Repeats {repeatFrequency} Starting {startDate}
            </Text>
          </View>
          <View style={styles.separator} />

          {/* Start Date */}
          <View style={styles.detailRow}>
            <Text style={styles.detailLabel}>Start Date</Text>
            <Text style={styles.detailValue}>{startDate}</Text>
          </View>
          <View style={styles.separator} />

          {/* Rollover */}
          <View style={styles.detailRow}>
            <Text style={styles.detailLabel}>Rollover budget amount</Text>
            <Text style={styles.detailValue}>{rolloverBudget ? 'Yes' : 'No'}</Text>
          </View>
          <View style={styles.separator} />

          {/* Alert */}
          <View style={styles.alertContainer}>
            <View style={styles.alertHeader}>
              <View style={styles.alertIconContainer}>
                <Ionicons name="notifications-outline" size={24} color="#64748b" />
              </View>
              <Text style={styles.alertText}>
                Alert me when expense reaches <Text style={styles.boldText}>{alertPercentage}%</Text> of budget
              </Text>
            </View>
            <Slider
              style={styles.slider}
              minimumValue={0}
              maximumValue={100}
              step={5}
              value={alertPercentage}
              disabled={true}
              minimumTrackTintColor="#0284c7"
              maximumTrackTintColor="#e5e7eb"
              thumbTintColor="#0284c7"
            />
          </View>
        </View>

        {/* Create Button */}
        <TouchableOpacity 
          style={styles.createButton}
          onPress={handleCreate}
        >
          <Text style={styles.createButtonText}>CREATE</Text>
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
    paddingBottom: 24,
  },
  budgetHeader: {
    alignItems: 'center',
    paddingVertical: 24,
  },
  budgetIconContainer: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: '#f1f5f9',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 16,
  },
  budgetName: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#1e293b',
    marginBottom: 4,
  },
  budgetType: {
    fontSize: 16,
    color: '#64748b',
  },
  detailsContainer: {
    paddingHorizontal: 16,
  },
  detailRow: {
    paddingVertical: 16,
  },
  detailLabel: {
    fontSize: 16,
    color: '#64748b',
    marginBottom: 8,
  },
  detailValue: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#1e293b',
  },
  separator: {
    height: 1,
    backgroundColor: '#e2e8f0',
  },
  alertContainer: {
    padding: 16,
    backgroundColor: 'white',
    borderRadius: 16,
    marginTop: 16,
    borderWidth: 1,
    borderColor: '#e2e8f0',
  },
  alertHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 16,
  },
  alertIconContainer: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: '#f1f5f9',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
  },
  alertText: {
    flex: 1,
    fontSize: 16,
    color: '#1e293b',
  },
  boldText: {
    fontWeight: 'bold',
  },
  slider: {
    width: '100%',
    height: 40,
  },
  createButton: {
    backgroundColor: '#0284c7',
    borderRadius: 8,
    paddingVertical: 16,
    marginHorizontal: 16,
    marginTop: 32,
    marginBottom: 40,
    alignItems: 'center',
  },
  createButtonText: {
    fontSize: 16,
    fontWeight: 'bold',
    color: 'white',
  },
});